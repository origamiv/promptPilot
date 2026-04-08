"""Worker — executes tasks from the queue."""

import json
import os
import pwd
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone

from . import db
from . import relogin
from .config import (
    AGENT_TIMEOUT,
    AGENT_USER,
    BASE_DELAY,
    CLAUDE_TASK_TIMEOUT,
    DEFAULT_CLI,
    MAX_DELAY,
    PM_TASK_TIMEOUT,
    POLL_INTERVAL,
    WORKER_CONCURRENCY,
    TASK_TIMEOUT,
    build_cmd,
    get_provider_env,
)
from .limits import refresh_limits_for_provider
from .models import TaskCreate
from .rabbitmq import RabbitQueue, queue_name_for_project

RATE_LIMIT_PATTERNS = [
    "rate limit",
    "rate_limit",
    "ratelimit",
    "overloaded",
    "too many requests",
    "429",
    "quota exceeded",
    "capacity",
    "try again later",
]

AUTH_ERROR_PATTERNS = [
    "401",
    "unauthorized",
    "forbidden",
    "authentication failed",
    "failed to authenticate",
    "invalid api key",
    "token expired",
    "token is invalid",
]

BWRAP_ARGV0_PATTERN = "bwrap: unknown option --argv0"


def is_rate_limited(stderr: str, exit_code: int) -> bool:
    if exit_code == 0:
        return False
    text = stderr.lower()
    # Auth and token failures must be treated as hard failures, not retries.
    if any(p in text for p in AUTH_ERROR_PATTERNS):
        return False
    # 429 should match as a standalone code (avoid accidental substring hits).
    if re.search(r"\b429\b", text):
        return True
    return any(p in text for p in RATE_LIMIT_PATTERNS)


def compute_next_run(retry_count: int) -> datetime:
    delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
    jitter = delay * 0.1 * (random.random() * 2 - 1)
    return datetime.now(timezone.utc) + timedelta(seconds=delay + jitter)


def parse_stream_json(stdout: str) -> dict:
    """Parse stream-json output from Claude CLI.

    Extracts text from assistant messages, metadata from result event,
    and rate limit info.
    """
    text_parts = []
    meta = {}
    rate_limit_info = None
    denials = []

    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON line — treat as plain text
            text_parts.append(line)
            continue

        etype = event.get("type")

        if etype == "assistant":
            # Extract text content from assistant messages
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])

        elif etype == "result":
            # Final result event — metadata
            meta["cost"] = event.get("total_cost_usd")
            meta["session_id"] = event.get("session_id")
            meta["duration_ms"] = event.get("duration_ms")
            meta["num_turns"] = event.get("num_turns")
            meta["is_error"] = event.get("is_error")
            meta["subtype"] = event.get("subtype")
            usage = event.get("usage", {})
            meta["input_tokens"] = usage.get("input_tokens")
            meta["output_tokens"] = usage.get("output_tokens")
            model_usage = event.get("modelUsage", {})
            if model_usage:
                meta["model"] = list(model_usage.keys())[0]
            # If result has text and we didn't capture any
            if event.get("result") and not text_parts:
                text_parts.append(event["result"])
            for d in event.get("permission_denials", []):
                desc = d.get("tool_input", {}).get("description") or d.get("tool_input", {}).get("command", "")
                denials.append(f"[{d.get('tool_name', '?')}] {desc}")

        elif etype == "rate_limit_event":
            rate_limit_info = event.get("rate_limit_info", {})
            meta["rate_limit"] = rate_limit_info

    text = "\n".join(text_parts).strip()
    if denials:
        meta["denials"] = denials

    return {"text": text, "meta": meta, "rate_limit_info": rate_limit_info}


def format_result(parsed: dict, raw_stream: str = "", stderr: str = "", include_raw_output: bool = False) -> str:
    """Format parsed result for storage.

    By default stores human-readable text + meta.
    Optionally can append full raw agent output for complete task logs.
    """
    parts = []

    if parsed["text"]:
        parts.append(parsed["text"])

    if include_raw_output:
        full_stdout = (raw_stream or "").strip()
        full_stderr = (stderr or "").strip()
        if full_stdout:
            parts.append("")
            parts.append("--- Agent Output (stdout) ---")
            parts.append(full_stdout)
        if full_stderr:
            parts.append("")
            parts.append("--- Agent Output (stderr) ---")
            parts.append(full_stderr)

    meta = parsed["meta"]
    if meta:
        parts.append("")
        parts.append("--- Meta ---")
        if meta.get("model"):
            parts.append(f"Model: {meta['model']}")
        if meta.get("cost") is not None:
            parts.append(f"Cost: ${meta['cost']:.4f}")
        if meta.get("duration_ms") is not None:
            parts.append(f"Time: {meta['duration_ms'] / 1000:.1f}s")
        if meta.get("input_tokens") is not None:
            parts.append(f"Tokens: {meta['input_tokens']} in / {meta.get('output_tokens', '?')} out")
        if meta.get("session_id"):
            parts.append(f"Session: {meta['session_id']}")
        if meta.get("rate_limit"):
            rl = meta["rate_limit"]
            resets = rl.get("resetsAt")
            if resets:
                dt = datetime.fromtimestamp(resets)
                parts.append(f"Rate limit resets: {dt.strftime('%Y-%m-%d %H:%M')}")
        if meta.get("denials"):
            parts.append(f"\nPermission denials ({len(meta['denials'])}):")
            for d in meta["denials"]:
                parts.append(f"  {d}")

    return "\n".join(parts)


def is_stream_json(stdout: str) -> bool:
    """Check if output looks like stream-json (multiple JSON lines)."""
    if not stdout:
        return False
    first_line = stdout.strip().split("\n", 1)[0].strip()
    if not first_line:
        return False
    try:
        data = json.loads(first_line)
        return isinstance(data, dict) and "type" in data
    except (json.JSONDecodeError, TypeError):
        return False


def humanize_error(stdout: str, stderr: str) -> str:
    """Return a readable error message instead of raw JSONL streams."""
    for payload in (stderr or "", stdout or ""):
        if not payload or not is_stream_json(payload):
            continue

        parsed = parse_stream_json(payload)
        text = (parsed.get("text") or "").strip()
        rl = parsed.get("rate_limit_info") or {}
        rl_status = str(rl.get("status") or "").strip().lower()
        if text:
            if rl_status and rl_status != "allowed":
                return f"Rate limit: {text}"
            return text

        # Fallback: extract `error` field from JSON events.
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            err = event.get("error")
            if isinstance(err, str) and err.strip():
                return err.strip()

        formatted = format_result(parsed).strip()
        if formatted:
            return formatted

    return (stderr or stdout or "Execution failed").strip()


def stream_is_rate_limited(parsed: dict) -> bool:
    rl = (parsed or {}).get("rate_limit_info") or {}
    status = str(rl.get("status") or "").strip().lower()
    if status and status != "allowed":
        return True
    text = ((parsed or {}).get("text") or "").lower()
    return "you've hit your limit" in text or "rate limit exceeded" in text


def build_src_payload(provider: str, stdout: str, stderr: str) -> dict:
    stream = bool(stdout and is_stream_json(stdout))
    payload = {
        "provider": provider,
        "format": "stream-json" if stream else "text",
    }
    if stream:
        events = []
        for line in (stdout or "").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                events.append(json.loads(s))
            except json.JSONDecodeError:
                events.append({"type": "raw_line", "line": s})
        payload["events"] = events
    else:
        payload["stdout"] = stdout or ""
    if stderr:
        payload["stderr"] = stderr
    return payload


def _load_worker_system_prompt(worker_id: int) -> str | None:
    """Загрузить системный промпт воркера: из файла или напрямую из поля prompt."""
    worker = db.get_worker(worker_id)
    if not worker or not worker.get("prompt"):
        return None
    field = worker["prompt"].strip()
    if field.startswith("/") or field.startswith("./"):
        try:
            with open(field, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            print(f"  -> Worker system prompt loaded from: {field}")
            return content
        except Exception as e:
            print(f"  -> Warning: could not read worker prompt file '{field}': {e}")
            return None
    return field


def _build_prompt_from_list(task, skip_base: bool = False) -> str:
    """Собрать итоговый промпт из task.prompt_list.

    Элементы списка (через запятую):
      base    → системный промпт воркера (если есть), иначе промпт 'base' из БД
      current → task.prompt (задача пользователя)
      project → comment проекта по task.working_dir
      <other> → промпт из таблицы prompts по shortname

    skip_base=True: не включать 'base' в результат (используется когда worker sys prompt
    передаётся отдельно через --system-prompt флаг).
    """
    items = [x.strip() for x in task.prompt_list.split(",") if x.strip()]

    # Загружаем системный промпт воркера один раз
    worker_sys = _load_worker_system_prompt(task.worker_id) if task.worker_id else None

    # Определяем какие shortname нужно тянуть из БД (всё кроме base/current/project если есть воркер)
    db_keys = [
        it.lower() for it in items
        if it.lower() not in ("current", "project")
        and not (it.lower() == "base" and worker_sys)
    ]
    by_short = db.get_prompts_by_shortnames(db_keys) if db_keys else {}

    parts = []
    missing = []
    for item in items:
        key = item.lower()
        if key == "current":
            parts.append(task.prompt)
        elif key == "project":
            project = db.get_project_by_folder(task.working_dir or "")
            comment = (project or {}).get("comment") or ""
            if comment:
                parts.append(comment)
        elif key == "base" and worker_sys:
            if not skip_base:
                parts.append(worker_sys)
        else:
            if key in by_short:
                parts.append(by_short[key])
            else:
                missing.append(item)

    if missing:
        print(f"  -> Warning: prompts not found in DB: {', '.join(missing)}")

    return "\n\n".join(p for p in parts if p)


def execute_task(task):
    """Run CLI with the task's prompt."""
    # Determine provider: worker's linked agent takes priority over task's agent.
    provider = task.provider or DEFAULT_CLI
    if task.worker_id:
        worker = db.get_worker(int(task.worker_id))
        if worker and worker.get("agent_shortname"):
            provider = worker["agent_shortname"]
            print(f"  -> Provider from worker #{task.worker_id} agent: {provider}")
        elif worker and not worker.get("agent_shortname"):
            # Worker has no agent linked — fall back to task's agent account
            if task.agent_account_id:
                acc = db.get_agent_account(int(task.agent_account_id))
                if acc and acc.get("agent_shortname"):
                    provider = acc["agent_shortname"]
                    print(f"  -> Provider from task agent account: {provider}")
    provider_key = provider.strip().lower()

    account = None
    if task.agent_account_id:
        account = db.get_agent_account(int(task.agent_account_id))
    if not account:
        account = db.pick_available_agent_account(provider)
    if account:
        try:
            db.set_task_agent_account(task.id, int(account["id"]))
        except Exception:
            pass

    def _is_exhausted_status(acc: dict) -> bool:
        status = acc.get("status")
        try:
            if status is not None and int(status) == 3:
                return True
        except Exception:
            pass
        for key in ("percent_5h", "percent_7d"):
            val = acc.get(key)
            try:
                if val is not None and float(val) >= 100.0:
                    return True
            except Exception:
                pass
        return False

    def _refresh_limits_for(acc: dict, exhausted_hint: bool = False) -> dict:
        if not acc:
            return acc
        acc = dict(acc)
        try:
            limits = refresh_limits_for_provider(provider, token=acc.get("token"))
            if limits:
                status = limits.get("status")
                if exhausted_hint and status == 1:
                    status = 3
                db.update_agent_account_limits(
                    int(acc["id"]),
                    status=status,
                    percent_5h=limits.get("percent_5h"),
                    percent_7d=limits.get("percent_7d"),
                    balance_tokens=limits.get("balance_tokens"),
                    reset_5h=limits.get("reset_5h"),
                    reset_7d=limits.get("reset_7d"),
                )
                acc.update(
                    {
                        "status": status if status is not None else acc.get("status"),
                        "percent_5h": limits.get("percent_5h"),
                        "percent_7d": limits.get("percent_7d"),
                        "balance_tokens": limits.get("balance_tokens"),
                        "reset_5h": limits.get("reset_5h"),
                        "reset_7d": limits.get("reset_7d"),
                    }
                )
            elif exhausted_hint:
                db.update_agent_account_limits(int(acc["id"]), status=3)
                acc["status"] = 3
        except Exception as e:
            print(f"  -> Limits refresh failed: {e}")
        return acc

    def _refresh_limits(exhausted_hint: bool = False):
        nonlocal account
        if not account:
            return
        account = _refresh_limits_for(account, exhausted_hint=exhausted_hint)

    def _switch_account_if_exhausted() -> bool:
        nonlocal account
        if not account:
            return False
        account = _refresh_limits_for(account)
        if not _is_exhausted_status(account):
            return True

        agent_id = account.get("agent_id")
        if not agent_id:
            print("  -> Active account is exhausted, but agent_id is missing")
            return False
        current_id = int(account["id"])
        candidates = db.list_agent_accounts_for_relogin(int(agent_id), exclude_account_id=current_id, limit=20)
        if not candidates:
            print("  -> Active account exhausted and no other accounts with credentials found")
            return False

        for cand in candidates:
            cand_id = int(cand["id"])
            try:
                if provider_key.startswith("claude"):
                    relogin.start_relogin(cand_id)
                else:
                    # For non-Claude providers we can at least switch active account marker.
                    db.set_agent_account_active(cand_id, True)
            except Exception as e:
                print(f"  -> Account switch failed for #{cand_id}: {e}")
                continue

            switched = db.get_agent_account(cand_id) or cand
            switched = _refresh_limits_for(switched)
            if _is_exhausted_status(switched):
                print(f"  -> Account #{cand_id} is also exhausted")
                continue

            account = switched
            db.set_task_agent_account(task.id, cand_id)
            print(f"  -> Switched to account #{cand_id} for agent #{agent_id}")
            return True

        print("  -> All candidate accounts are exhausted or switch failed")
        return False

    def _failover_on_rate_limit(rate_error: str = "") -> bool:
        nonlocal account
        if not account:
            print("  -> Rate limited, but task has no bound agent account for failover")
            return False
        agent_id = account.get("agent_id")
        if not agent_id:
            print("  -> Rate limited, but active account has no agent_id")
            return False

        current_id = int(account["id"])
        candidates = db.list_agent_accounts_for_relogin(int(agent_id), exclude_account_id=current_id, limit=20)
        if not candidates:
            print("  -> No alternative accounts with credentials for rate-limit failover")
            return False

        for cand in candidates:
            cand_id = int(cand["id"])
            try:
                if provider_key.startswith("claude"):
                    relogin.start_relogin(cand_id)
                else:
                    db.set_agent_account_active(cand_id, True)
            except Exception as e:
                print(f"  -> Relogin failed for account #{cand_id}: {e}")
                continue

            switched = db.get_agent_account(cand_id) or cand
            switched = _refresh_limits_for(switched)
            if _is_exhausted_status(switched):
                print(f"  -> Account #{cand_id} is exhausted after relogin")
                continue

            try:
                cloned = db.create_task(
                    TaskCreate(
                        prompt=task.prompt,
                        subject=task.subject,
                        agent_prompt=task.agent_prompt or None,
                        working_dir=task.working_dir,
                        provider=task.provider,
                        priority=task.priority,
                        max_retries=task.max_retries,
                        skip_permissions=task.skip_permissions,
                        model=task.model,
                        session_id=task.session_id,
                        parent_task_id=task.id,
                        tg_chat_id=task.tg_chat_id,
                    )
                )
                db.set_task_agent_account(cloned.id, cand_id)
            except Exception as e:
                print(f"  -> Failed to create cloned task for account #{cand_id}: {e}")
                continue

            account = switched
            err_txt = (rate_error or "").strip()
            suffix = f" ({err_txt[:120]})" if err_txt else ""
            print(
                f"  -> Rate-limit failover: task #{task.id} cloned to #{cloned.id}, "
                f"switched account #{current_id} -> #{cand_id}{suffix}"
            )
            return True

        print("  -> Rate-limit failover failed: no account could accept cloned task")
        return False

    if account and not _switch_account_if_exhausted():
        next_run = account.get("reset_5h") if isinstance(account, dict) else None
        if not isinstance(next_run, datetime):
            next_run = compute_next_run(task.retry_count)
        db.mark_rate_limited(
            task.id,
            next_run,
            error="Active agent account limits are exhausted; no alternative account with valid credentials",
        )
        return

    system_prompt_override = None
    # For tasks with an assigned worker: pass the worker system prompt via
    # --system-prompt so it takes precedence over AGENTS.md loaded by Claude Code
    # CLI from the working directory.  This is critical for PM agent (worker_id=8)
    # which must orchestrate via API and must NOT follow developer rules from AGENTS.md.
    if task.worker_id:
        worker_sys = _load_worker_system_prompt(task.worker_id)
        if worker_sys:
            system_prompt_override = worker_sys
    # Build the user-level prompt (task instructions only, no duplicated system text).
    if task.prompt_list and not system_prompt_override:
        # prompt_list includes 'base' (worker sys) — use it only when not using --system-prompt.
        base_prompt = _build_prompt_from_list(task)
    elif task.prompt_list and system_prompt_override:
        # Worker sys goes via --system-prompt; rebuild list without 'base' component.
        base_prompt = _build_prompt_from_list(task, skip_base=True)
    else:
        base_prompt = task.prompt
    # Inject task metadata so the agent knows its own ID and working directory.
    task_meta = (
        f"\n\nМетаданные текущей задачи:\n"
        f"- Твой task_id: {task.id}\n"
        f"- working_dir: {task.working_dir or '(не указана)'}\n"
        f"- parent_task_id: {task.parent_task_id or '(нет, ты корневая задача)'}\n"
    )
    # Guardrail: allow restarting only the web server, never the worker process.
    runtime_guard = (
        "\n\nОбязательное ограничение выполнения:\n"
        "- Нельзя останавливать или перезапускать воркер PromptPilot "
        "(`pp worker`, `promptpilot-worker`, `systemctl *worker*`, `pkill`/`kill` воркера).\n"
        "- Если нужно перезапустить проект, перезапускай только веб-сервер "
        "(`pp server` или `promptpilot-server`).\n"
    )
    effective_prompt = f"{base_prompt}{task_meta}{runtime_guard}"
    cmd = build_cmd(provider, effective_prompt, skip_permissions=task.skip_permissions, session_id=task.session_id, model=task.model, system_prompt=system_prompt_override)

    env = get_provider_env(provider)
    preexec_fn = None

    # Optional per-task user switch (Linux): run agent CLI as AGENT_USER from .env.
    if AGENT_USER and os.name != "nt":
        if os.geteuid() == 0:
            try:
                pw = pwd.getpwnam(AGENT_USER)
            except KeyError:
                db.mark_failed(task.id, f"Configured AGENT_USER '{AGENT_USER}' does not exist", exit_code=-1)
                _refresh_limits()
                return

            target_uid = pw.pw_uid
            target_gid = pw.pw_gid
            target_home = pw.pw_dir or f"/home/{AGENT_USER}"

            def _drop_privileges():
                os.initgroups(AGENT_USER, target_gid)
                os.setgid(target_gid)
                os.setuid(target_uid)

            preexec_fn = _drop_privileges
            env["HOME"] = target_home
            env["USER"] = AGENT_USER
            env["LOGNAME"] = AGENT_USER
        else:
            # Not fatal: keep current user if worker isn't running as root.
            print(f"  -> AGENT_USER={AGENT_USER} ignored (worker uid={os.geteuid()}, root required for setuid)")

    # On Windows, .cmd/.bat wrappers (e.g. npm-installed CLIs like qwen) are
    # invisible to subprocess without shell=True.  shutil.which() resolves the
    # full path including extension so subprocess can find and run them directly.
    resolved = shutil.which(cmd[0], path=env.get("PATH"))
    if resolved:
        cmd[0] = resolved

    # PM orchestration tasks can legitimately run much longer than regular coding tasks.
    if task.worker_id == 8 and PM_TASK_TIMEOUT > 0:
        task_timeout = PM_TASK_TIMEOUT
    else:
        task_timeout = AGENT_TIMEOUT or (CLAUDE_TASK_TIMEOUT if provider.startswith("claude") else TASK_TIMEOUT)

    def _run_once(command):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=task_timeout,
            cwd=task.working_dir,
            stdin=subprocess.DEVNULL,
            env=env,
            preexec_fn=preexec_fn,
        )

    try:
        result = _run_once(cmd)
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout if isinstance(e.stdout, str) else ""
        stderr = e.stderr if isinstance(e.stderr, str) else ""
        db.mark_failed(
            task.id,
            f"Execution timed out ({task_timeout}s)",
            exit_code=-1,
            src=build_src_payload(provider, stdout, stderr),
        )
        _refresh_limits()
        return
    except FileNotFoundError:
        db.mark_failed(task.id, f"CLI '{provider}' not found. Is it installed and in PATH?", exit_code=-1)
        _refresh_limits()
        return

    # Codex fallback for older bubblewrap versions that don't support --argv0.
    # Retry once without sandbox if the known bwrap incompatibility is detected.
    if (
        result.returncode != 0
        and provider == "codex"
        and BWRAP_ARGV0_PATTERN in (result.stderr or "")
        and "--dangerously-bypass-approvals-and-sandbox" not in cmd
    ):
        fallback_cmd = list(cmd)
        prompt_idx = fallback_cmd.index(effective_prompt) if effective_prompt in fallback_cmd else len(fallback_cmd)
        fallback_cmd[prompt_idx:prompt_idx] = ["--dangerously-bypass-approvals-and-sandbox"]
        print("  -> Codex bwrap incompatibility detected, retrying without sandbox...")
        try:
            result = _run_once(fallback_cmd)
        except subprocess.TimeoutExpired:
            db.mark_failed(task.id, "Execution timed out", exit_code=-1)
            _refresh_limits()
            return
        except FileNotFoundError:
            db.mark_failed(task.id, f"CLI '{provider}' not found. Is it installed and in PATH?", exit_code=-1)
            _refresh_limits()
            return

    # Some CLIs (including Claude in --output-format stream-json) can emit
    # rate-limit details to stdout instead of stderr, so inspect both.
    err_text = result.stderr or ""
    out_text = result.stdout or ""
    readable_error = humanize_error(result.stdout, result.stderr)
    if not is_stream_json(result.stdout or "") and is_rate_limited(f"{err_text}\n{out_text}", result.returncode):
        src_payload = build_src_payload(provider, result.stdout or "", result.stderr or "")
        next_run = compute_next_run(task.retry_count)
        details = readable_error or "Rate limited"
        if task.retry_count >= task.max_retries:
            details = f"Rate limited, max retries ({task.max_retries}) exceeded.\n{details}"
        db.mark_rate_limited(task.id, next_run, error=details)
        _refresh_limits(exhausted_hint=True)
        _failover_on_rate_limit(details)
        print(f"  -> Rate limited. Retry #{task.retry_count + 1} at {next_run.strftime('%H:%M:%S')}")
        return

    if result.returncode != 0:
        if result.returncode == 143:
            db.mark_failed(
                task.id,
                "Task interrupted: worker/service was restarted",
                exit_code=result.returncode,
                src=build_src_payload(provider, result.stdout or "", result.stderr or ""),
            )
            _refresh_limits()
            print("  -> Failed (interrupted by restart)")
            return
        db.mark_failed(
            task.id,
            readable_error,
            exit_code=result.returncode,
            src=build_src_payload(provider, result.stdout or "", result.stderr or ""),
        )
        _refresh_limits()
        print(f"  -> Failed (exit {result.returncode})")
        return

    # Parse output
    model_used = None
    session_id = None
    if is_stream_json(result.stdout):
        parsed = parse_stream_json(result.stdout)
        output = format_result(
            parsed,
            raw_stream=result.stdout,
            stderr=result.stderr,
            include_raw_output=False,
        )
        src_payload = build_src_payload(provider, result.stdout or "", result.stderr or "")
        model_used = parsed["meta"].get("model")
        session_id = parsed["meta"].get("session_id")
        # If agent asked for approvals / had tool permission denials,
        # task is considered incomplete and must be marked as failed.
        denials = parsed["meta"].get("denials") or []
        if denials:
            details = "\n".join(str(d) for d in denials)
            db.mark_failed(
                task.id,
                f"Task stopped due to permission denials.\n{details}",
                exit_code=1,
                src=src_payload,
            )
            _refresh_limits()
            print("  -> Failed: permission denials")
            return
        # Check for rate limit in stream events — only if no text was returned
        if stream_is_rate_limited(parsed):
            next_run = compute_next_run(task.retry_count)
            details = output or "Rate limited"
            if task.retry_count >= task.max_retries:
                details = f"Rate limited, max retries ({task.max_retries}) exceeded.\n{details}"
            db.mark_rate_limited(task.id, next_run, error=details)
            _refresh_limits(exhausted_hint=True)
            _failover_on_rate_limit(details)
            print(f"  -> Rate limited (stream event). Retry at {next_run.strftime('%H:%M:%S')}")
            return
    else:
        # Plain text output (non-Claude CLIs): keep full stdout/stderr.
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        output = stdout
        if stderr:
            if output:
                output += "\n\n"
            output += f"--- Agent Output (stderr) ---\n{stderr}"
        src_payload = build_src_payload(provider, result.stdout or "", result.stderr or "")

    db.mark_completed(
        task.id,
        output,
        exit_code=0,
        model_used=model_used,
        session_id=session_id,
        src=src_payload,
    )
    _refresh_limits()
    text_preview = output[:80].replace("\n", " ").strip()
    print(f"  -> Completed: {text_preview}")

    if task.recurrence:
        next_dt = db.parse_recurrence(task.recurrence)
        if next_dt:
            from .models import TaskCreate
            db.create_task(TaskCreate(
                prompt=task.prompt,
                agent_prompt=task.agent_prompt or None,
                working_dir=task.working_dir,
                provider=task.provider,
                priority=task.priority,
                scheduled_at=next_dt,
                max_retries=task.max_retries,
                skip_permissions=task.skip_permissions,
                model=task.model,
                recurrence=task.recurrence,
                tg_chat_id=task.tg_chat_id,
            ))
            print(f"  -> Recurring: next run at {next_dt.strftime('%Y-%m-%d %H:%M UTC')}")


def run_worker():
    """Main worker loop."""
    running = True

    def stop(signum, frame):
        nonlocal running
        print("\nShutting down worker...")
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    # Recover any tasks stuck in 'running' from a previous crash
    db.recover_running()

    rabbit = RabbitQueue()
    queue_names = []
    queue_refresh_at = 0.0
    due_dispatch_at = 0.0
    last_dispatch_error_at = 0.0
    published_recently: dict[int, float] = {}

    print(f"PromptPilot worker started (poll every {POLL_INTERVAL}s)")
    print(f"Concurrency: {WORKER_CONCURRENCY} tasks")
    timeout_label = f"{AGENT_TIMEOUT}s (AGENT_TIMEOUT)" if AGENT_TIMEOUT else f"{TASK_TIMEOUT}s"
    print(f"Timeout: {timeout_label} | Backoff: {BASE_DELAY}-{MAX_DELAY}s")
    if rabbit.enabled:
        print("Queue backend: RabbitMQ")
    else:
        print("Queue backend: DB polling fallback")
    print("Waiting for tasks...\n")

    def _drain_done(active):
        done = [f for f in list(active.keys()) if f.done()]
        for f in done:
            task_id = active.pop(f)
            try:
                f.result()
            except Exception as e:
                print(f"[#{task_id}] Worker execution error: {e}")

    try:
        with ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY, thread_name_prefix="pp-task") as pool:
            active = {}
            while running or active:
                _drain_done(active)

                if not running:
                    if active:
                        wait(list(active.keys()), timeout=0.5, return_when=FIRST_COMPLETED)
                    continue

                now_ts = time.time()
                if db.is_paused():
                    if active:
                        wait(list(active.keys()), timeout=1.0, return_when=FIRST_COMPLETED)
                    else:
                        rabbit.wait(1.0)
                    continue

                if rabbit.enabled and now_ts >= queue_refresh_at:
                    try:
                        queue_names = db.get_project_queue_names(include_default=True)
                        for q in queue_names:
                            rabbit.ensure_queue(q)
                        print(f"  -> Queues refreshed: {len(queue_names)}")
                    except Exception as e:
                        print(f"  -> Queue refresh failed: {e}")
                        queue_names = [queue_name_for_project(None)]
                    queue_refresh_at = now_ts + 60.0

                if rabbit.enabled and now_ts >= due_dispatch_at:
                    try:
                        due_jobs = db.list_due_task_jobs(limit=400)
                        sent = 0
                        for job in due_jobs:
                            task_id = int(job["task_id"])
                            prev = published_recently.get(task_id, 0.0)
                            if (now_ts - prev) < max(1.0, float(POLL_INTERVAL)):
                                continue
                            queue_name = queue_name_for_project(job.get("project_id"))
                            if rabbit.publish(queue_name, job):
                                published_recently[task_id] = now_ts
                                sent += 1
                        if sent:
                            print(f"  -> Dispatched due tasks into RabbitMQ: {sent}")
                        stale_before = now_ts - max(60.0, POLL_INTERVAL * 10.0)
                        published_recently = {k: v for k, v in published_recently.items() if v >= stale_before}
                    except Exception as e:
                        print(f"  -> Due-dispatch failed: {e}")
                        last_dispatch_error_at = now_ts
                    due_dispatch_at = now_ts + max(1.0, float(POLL_INTERVAL))

                slots = max(0, WORKER_CONCURRENCY - len(active))
                if slots <= 0:
                    wait(list(active.keys()), timeout=0.5, return_when=FIRST_COMPLETED)
                    continue

                claimed = 0
                for _ in range(slots):
                    if rabbit.enabled:
                        msg = rabbit.get_one(queue_names or [queue_name_for_project(None)])
                        if not msg:
                            # Fallback path: if dispatcher recently failed (e.g. DB deadlock),
                            # claim runnable tasks directly from DB to avoid queue starvation.
                            if (now_ts - last_dispatch_error_at) <= 120.0:
                                task = db.get_next_runnable()
                                if task is None:
                                    break
                            else:
                                break
                        else:
                            payload = msg.payload if isinstance(msg.payload, dict) else {}
                            raw_task_id = payload.get("task_id")
                            try:
                                task_id = int(raw_task_id)
                            except Exception:
                                print(f"  -> Skip malformed queue message from {msg.queue}: {payload!r}")
                                rabbit.ack(msg.delivery_tag)
                                continue

                            task = db.claim_task_for_run(task_id)
                            rabbit.ack(msg.delivery_tag)
                            if task is None:
                                continue
                    else:
                        task = db.get_next_runnable()
                        if task is None:
                            break

                    provider = task.provider or DEFAULT_CLI
                    prompt_preview = task.prompt[:60].replace("\n", " ")
                    print(f"[#{task.id}] [{provider}] Running: {prompt_preview}...")
                    fut = pool.submit(execute_task, task)
                    active[fut] = task.id
                    claimed += 1

                if claimed == 0:
                    if rabbit.enabled:
                        if active:
                            wait(list(active.keys()), timeout=0.8, return_when=FIRST_COMPLETED)
                        else:
                            rabbit.wait(0.8)
                    else:
                        if active:
                            wait(list(active.keys()), timeout=max(0.3, float(POLL_INTERVAL) / 2), return_when=FIRST_COMPLETED)
                        else:
                            time.sleep(POLL_INTERVAL)
    finally:
        rabbit.close()
        print("Worker stopped.")
