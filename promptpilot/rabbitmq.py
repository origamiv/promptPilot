"""RabbitMQ queue integration for PromptPilot."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from .config import (
    QUEUE_CONNECTION,
    RABBITMQ_HEARTBEAT,
    RABBITMQ_HOST,
    RABBITMQ_PASSWORD,
    RABBITMQ_PORT,
    RABBITMQ_PREFETCH,
    RABBITMQ_QUEUE_PREFIX,
    RABBITMQ_USER,
    RABBITMQ_VHOST,
)

try:
    import pika
except Exception:  # pragma: no cover - runtime dependency is optional during tests
    pika = None


def queue_name_for_project(project_id: Optional[int]) -> str:
    prefix = RABBITMQ_QUEUE_PREFIX if RABBITMQ_QUEUE_PREFIX.startswith("pp_") else f"pp_{RABBITMQ_QUEUE_PREFIX}"
    normalized = "".join(ch if (ch.isalnum() or ch in ("_", "-", ".")) else "_" for ch in prefix)
    if not normalized.endswith("_"):
        normalized += "_"
    if project_id and int(project_id) > 0:
        return f"{normalized}project_{int(project_id)}"
    return f"{normalized}default"


@dataclass
class QueueMessage:
    queue: str
    payload: dict
    delivery_tag: int


class RabbitQueue:
    """Small blocking RabbitMQ helper for single-threaded worker loops."""

    def __init__(self):
        self._conn = None
        self._channel = None
        self.enabled = QUEUE_CONNECTION == "rabbitmq"
        self._missing_warned = False

    def _build_params(self):
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        return pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
            heartbeat=RABBITMQ_HEARTBEAT,
            blocked_connection_timeout=15,
            socket_timeout=10,
        )

    def _ensure_connected(self):
        if not self.enabled:
            return None
        if pika is None:
            if not self._missing_warned:
                print("RabbitMQ disabled: install package 'pika' to enable queue mode.")
                self._missing_warned = True
            self.enabled = False
            return None
        try:
            if self._conn and self._conn.is_open and self._channel and self._channel.is_open:
                return self._channel
        except Exception:
            pass
        self.close()
        self._conn = pika.BlockingConnection(self._build_params())
        self._channel = self._conn.channel()
        self._channel.basic_qos(prefetch_count=max(1, int(RABBITMQ_PREFETCH)))
        return self._channel

    def ensure_queue(self, queue_name: str):
        ch = self._ensure_connected()
        if not ch:
            return
        ch.queue_declare(queue=queue_name, durable=True)

    def publish(self, queue_name: str, payload: dict) -> bool:
        ch = self._ensure_connected()
        if not ch:
            return False
        ch.queue_declare(queue=queue_name, durable=True)
        body = json.dumps(payload, ensure_ascii=False)
        props = pika.BasicProperties(content_type="application/json", delivery_mode=2)
        ch.basic_publish(exchange="", routing_key=queue_name, body=body.encode("utf-8"), properties=props)
        return True

    def get_one(self, queue_names: list[str]) -> Optional[QueueMessage]:
        ch = self._ensure_connected()
        if not ch:
            return None
        for q in queue_names:
            ch.queue_declare(queue=q, durable=True)
            method, properties, body = ch.basic_get(queue=q, auto_ack=False)
            if not method:
                continue
            payload = {}
            if body:
                try:
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    payload = {"raw": body.decode("utf-8", errors="replace")}
            return QueueMessage(queue=q, payload=payload, delivery_tag=method.delivery_tag)
        return None

    def ack(self, delivery_tag: int):
        ch = self._ensure_connected()
        if not ch:
            return
        ch.basic_ack(delivery_tag=delivery_tag)

    def nack(self, delivery_tag: int, requeue: bool = True):
        ch = self._ensure_connected()
        if not ch:
            return
        ch.basic_nack(delivery_tag=delivery_tag, requeue=requeue)

    def wait(self, seconds: float):
        # Keep heartbeat alive while idling.
        end = time.time() + max(0.0, float(seconds))
        while time.time() < end:
            if self._conn and self._conn.is_open:
                try:
                    self._conn.process_data_events(time_limit=0.2)
                except Exception:
                    self.close()
            time.sleep(0.2)

    def close(self):
        try:
            if self._channel and self._channel.is_open:
                self._channel.close()
        except Exception:
            pass
        finally:
            self._channel = None
        try:
            if self._conn and self._conn.is_open:
                self._conn.close()
        except Exception:
            pass
        finally:
            self._conn = None
