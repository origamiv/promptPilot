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
from datetime import datetime, timedelta, timezone

from . import db
from .config import AGENT_USER, BASE_DELAY, DEFAULT_CLI, MAX_DELAY, POLL_INTERVAL, TASK_TIMEOUT, build_cmd, get_provider_env
from .limits import refresh_limits_for_provider

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
        if text:
            if parsed.get("rate_limit_info"):
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


def execute_task(task):
    """Run CLI with the task's prompt."""
    provider = task.provider or DEFAULT_CLI
    account = db.pick_available_agent_account(provider)
    if account:
        try:
            db.set_task_agent_account(task.id, int(account["id"]))
        except Exception:
            pass

    def _refresh_limits(exhausted_hint: bool = False):
        if not account:
            return
        try:
            limits = refresh_limits_for_provider(provider, token=account.get("token"))
            if limits:
                status = limits.get("status")
                if exhausted_hint and status == 1:
                    status = 3
                db.update_agent_account_limits(
                    int(account["id"]),
                    status=status,
                    percent_5h=limits.get("percent_5h"),
                    percent_7d=limits.get("percent_7d"),
                    balance_tokens=limits.get("balance_tokens"),
                    reset_5h=limits.get("reset_5h"),
                    reset_7d=limits.get("reset_7d"),
                )
            elif exhausted_hint:
                db.update_agent_account_limits(int(account["id"]), status=3)
        except Exception as e:
            print(f"  -> Limits refresh failed: {e}")

    cmd = build_cmd(provider, task.prompt, skip_permissions=task.skip_permissions, session_id=task.session_id, model=task.model)

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

    def _run_once(command):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TASK_TIMEOUT,
            cwd=task.working_dir,
            stdin=subprocess.DEVNULL,
            env=env,
            preexec_fn=preexec_fn,
        )

    try:
        result = _run_once(cmd)
    except subprocess.TimeoutExpired:
        db.mark_failed(task.id, "Execution timed out", exit_code=-1)
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
        prompt_idx = fallback_cmd.index(task.prompt) if task.prompt in fallback_cmd else len(fallback_cmd)
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
    if is_rate_limited(f"{err_text}\n{out_text}", result.returncode):
        src_payload = build_src_payload(provider, result.stdout or "", result.stderr or "")
        if task.retry_count >= task.max_retries:
            details = readable_error or "Rate limited"
            db.mark_failed(
                task.id,
                f"Rate limited, max retries ({task.max_retries}) exceeded.\n{details}",
                src=src_payload,
            )
            _refresh_limits(exhausted_hint=True)
            return
        next_run = compute_next_run(task.retry_count)
        db.mark_rate_limited(task.id, next_run, error=readable_error or "Rate limited")
        _refresh_limits(exhausted_hint=True)
        print(f"  -> Rate limited. Retry #{task.retry_count + 1} at {next_run.strftime('%H:%M:%S')}")
        return

    if result.returncode != 0:
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
        rl = parsed.get("rate_limit_info")
        if rl and not parsed["text"]:
            if task.retry_count >= task.max_retries:
                db.mark_failed(task.id, f"Rate limited.\n{output}", src=src_payload)
                _refresh_limits(exhausted_hint=True)
                return
            next_run = compute_next_run(task.retry_count)
            db.mark_rate_limited(task.id, next_run, error=output or "Rate limited")
            _refresh_limits(exhausted_hint=True)
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

    print(f"PromptPilot worker started (poll every {POLL_INTERVAL}s)")
    print(f"Timeout: {TASK_TIMEOUT}s | Backoff: {BASE_DELAY}-{MAX_DELAY}s")
    print("Waiting for tasks...\n")

    while running:
        if db.is_paused():
            time.sleep(POLL_INTERVAL)
            continue

        task = db.get_next_runnable()
        if task is None:
            time.sleep(POLL_INTERVAL)
            continue

        provider = task.provider or DEFAULT_CLI
        prompt_preview = task.prompt[:60].replace("\n", " ")
        print(f"[#{task.id}] [{provider}] Running: {prompt_preview}...")
        execute_task(task)

    print("Worker stopped.")
