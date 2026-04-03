"""Account limits refresh helpers (Claude/Codex)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Handle both ISO with Z and +00:00
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_usage(payload: object) -> dict:
    if isinstance(payload, list):
        data = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            key = str(item.get("title") or "").strip()
            if key:
                data[key] = item
        return data
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_limit(data: dict, keys: tuple[str, ...]) -> tuple[Optional[float], Optional[datetime]]:
    node = None
    for k in keys:
        if k in data and isinstance(data[k], dict):
            node = data[k]
            break
    if not node:
        return None, None
    util = node.get("utilization")
    try:
        util = float(util) if util is not None else None
    except Exception:
        util = None
    reset = _dt(node.get("resets_at"))
    return util, reset


def _status_from_percents(p5: Optional[float], p7: Optional[float]) -> int:
    vals = [x for x in (p5, p7) if x is not None]
    if vals and max(vals) >= 100.0:
        return 3
    return 1


def _load_claude_token_from_credentials() -> Optional[str]:
    cred_file = Path("/root/.claude/.credentials.json")
    if not cred_file.exists():
        return None
    try:
        creds = json.loads(cred_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    return creds.get("claudeAiOauth", {}).get("accessToken")


def fetch_claude_limits(token: Optional[str] = None) -> Optional[dict]:
    access_token = token or _load_claude_token_from_credentials()
    if not access_token:
        return None
    req = Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "claude-code/2.1.78",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            raw = json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    data = _normalize_usage(raw)
    percent_5h, reset_5h = _extract_limit(data, ("five_hour", "5h", "fiveHour"))
    percent_7d, reset_7d = _extract_limit(data, ("seven_day", "7d", "sevenDay", "weekly"))
    balance_tokens = None
    for k in ("balance_tokens", "token_balance", "remaining_tokens"):
        if k in data and isinstance(data[k], (int, float)):
            balance_tokens = int(data[k])
            break
    if balance_tokens is None and isinstance(raw, dict):
        for k in ("balance_tokens", "token_balance", "remaining_tokens"):
            if isinstance(raw.get(k), (int, float)):
                balance_tokens = int(raw.get(k))
                break
    return {
        "percent_5h": percent_5h,
        "percent_7d": percent_7d,
        "balance_tokens": balance_tokens,
        "reset_5h": reset_5h,
        "reset_7d": reset_7d,
        "status": _status_from_percents(percent_5h, percent_7d),
    }


def _parse_codex_status_pane(pane: str) -> Optional[dict]:
    pane = re.sub(r"\x1B\[[0-9;?]*[ -/]*[@-~]", "", pane or "")
    pane = pane.replace("\r", "")

    five_hour = re.search(r"5h limit:\s.*?(\d+(?:\.\d+)?)% left\s+\(resets (\d{1,2}:\d{2})\)", pane, re.I)
    weekly_left = re.search(r"Weekly limit:\s.*?(\d+(?:\.\d+)?)% left", pane, re.I)
    weekly_reset = re.search(r"\(resets (\d{1,2}:\d{2}) on (\d{1,2} [A-Za-z]{3})\)", pane)
    if not (five_hour and weekly_left and weekly_reset):
        return None

    five_left = float(five_hour.group(1))
    week_left = float(weekly_left.group(1))
    percent_5h = round(100.0 - five_left, 1)
    percent_7d = round(100.0 - week_left, 1)

    now = datetime.now(timezone.utc)
    hh, mm = map(int, five_hour.group(2).split(":"))
    reset_5h = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if reset_5h <= now:
        reset_5h = reset_5h + timedelta(days=1)

    day_month = weekly_reset.group(2)
    hh2, mm2 = map(int, weekly_reset.group(1).split(":"))
    try:
        reset_7d = datetime.strptime(f"{day_month} {now.year} {hh2:02d}:{mm2:02d}", "%d %b %Y %H:%M").replace(
            tzinfo=timezone.utc
        )
        if reset_7d < now - timedelta(days=1):
            reset_7d = reset_7d.replace(year=now.year + 1)
    except Exception:
        reset_7d = None

    return {
        "percent_5h": percent_5h,
        "percent_7d": percent_7d,
        "balance_tokens": None,
        "reset_5h": reset_5h,
        "reset_7d": reset_7d,
        "status": _status_from_percents(percent_5h, percent_7d),
    }


def fetch_codex_limits() -> Optional[dict]:
    codex_bin = shutil.which("codex")
    tmux_bin = shutil.which("tmux")
    if not codex_bin or not tmux_bin:
        return None

    session = f"codex_usage_{datetime.now(timezone.utc).strftime('%H%M%S%f')}"
    script = f"""
set -euo pipefail
SESSION='{session}'
TMUX='{tmux_bin}'
CODEX='{codex_bin}'
cleanup() {{
  "$TMUX" kill-session -t "$SESSION" >/dev/null 2>&1 || true
}}
trap cleanup EXIT
"$TMUX" new-session -d -s "$SESSION" -c /tmp "$CODEX" --no-alt-screen
sleep 2
"$TMUX" send-keys -t "$SESSION" Enter
sleep 2
LAST=""
for _ in 1 2 3; do
  "$TMUX" send-keys -t "$SESSION" C-u
  "$TMUX" send-keys -t "$SESSION" /status
  "$TMUX" send-keys -t "$SESSION" Enter
  sleep 2
  PANE=$("$TMUX" capture-pane -t "$SESSION" -p -S -260 2>/dev/null || true)
  LAST="$PANE"
  if printf '%s' "$PANE" | grep -q '5h limit:' && printf '%s' "$PANE" | grep -q 'Weekly limit:'; then
    printf '%s' "$PANE"
    exit 0
  fi
  sleep 2
done
printf '%s' "$LAST"
"""
    try:
        proc = subprocess.run(
            ["/bin/bash", "-lc", script],
            capture_output=True,
            text=True,
            timeout=45,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return _parse_codex_status_pane(proc.stdout or "")


def refresh_limits_for_provider(provider: str, token: Optional[str] = None) -> Optional[dict]:
    p = (provider or "").strip().lower()
    if p.startswith("claude"):
        return fetch_claude_limits(token=token)
    if p.startswith("codex"):
        return fetch_codex_limits()
    return None
