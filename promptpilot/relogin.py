"""Interactive relogin flow for agent accounts (currently Claude)."""

from __future__ import annotations

import os
import json
import pwd
import pty
import re
import secrets
import select
import subprocess
import threading
import time
import fcntl
import termios
import struct
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

from . import db
from .config import AGENT_USER, CLAUDE_EXE
from .limits import refresh_limits_for_provider


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
CLAUDE_URL_RE = re.compile(r"https://claude\.com/cai/oauth/authorize\?[^\"'<> ]+")
REL_LOGIN_ERR_RE = re.compile(
    r"(invalid|expired|denied|forbidden|error|failed|неверн|истек|ошибк|недейств)",
    re.IGNORECASE,
)
REL_LOGIN_OK_RE = re.compile(
    r"(authorized|authorised|logged in|login successful|successfully|setup complete|token created|auth complete|успеш|авторизац)",
    re.IGNORECASE,
)

def _claude_runtime_user() -> str:
    return (AGENT_USER or "").strip()


def _claude_home() -> Path:
    user = _claude_runtime_user()
    if user and os.name != "nt":
        try:
            return Path(pwd.getpwnam(user).pw_dir)
        except Exception:
            pass
    return Path.home()


CLAUDE_CREDENTIALS_PATH = _claude_home() / ".claude" / ".credentials.json"
DEVICE_CODE_RE = re.compile(
    r"(?:device\s*code|verification\s*code|код\s*устройства|код\s*подтверждения|code)\s*[:#]?\s*([A-Z0-9-]{4,})",
    re.IGNORECASE,
)


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _extract_auth_url(raw: str) -> Optional[str]:
    clean = _strip_ansi(raw).replace("\r", "\n")
    prefix = "https://claude.com/cai/oauth/authorize?"
    idx = clean.find(prefix)
    if idx < 0:
        return None
    tail = clean[idx : idx + 5000]
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~:/?#[]@!$&'()*+,;=%")
    buf: list[str] = []
    prev_nl = False
    for ch in tail:
        if ch in allowed:
            buf.append(ch)
            prev_nl = False
            continue
        if ch == "\n":
            # Wrapped URL lines may include single newlines; blank line marks end of URL block.
            if prev_nl and buf:
                break
            prev_nl = True
            continue
        if ch.isspace():
            continue
        if buf:
            break
    url = "".join(buf)
    m = CLAUDE_URL_RE.search(url)
    return m.group(0) if m else None


def _extract_device_code(raw: str) -> Optional[str]:
    clean = _strip_ansi(raw).replace("\r", "\n")
    for line in clean.splitlines():
        s = line.strip()
        if not s:
            continue
        m = DEVICE_CODE_RE.search(s)
        if m:
            return m.group(1).strip()
    return None


def _open_browser(url: str) -> None:
    # Browser launch is best-effort: service can run without DISPLAY.
    env = os.environ.copy()
    candidates = [
        ["firefox", "--new-tab", url],
        ["xdg-open", url],
    ]
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            return
        except Exception:
            continue


def _set_pty_winsize(fd: int, rows: int = 40, cols: int = 420) -> None:
    try:
        winsz = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsz)
    except Exception:
        pass


def _match_line(text: str, pattern: re.Pattern[str]) -> Optional[str]:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if pattern.search(s):
            return s
    return None


@dataclass
class ReloginSession:
    session_id: str
    account_id: int
    provider: str
    created_at: datetime
    proc: subprocess.Popen
    master_fd: int
    auth_url: str
    expected_login: Optional[str]
    requires_code: bool
    buffer: str = ""

    def append_output(self, text: str) -> None:
        self.buffer += text
        # keep in-memory log bounded
        if len(self.buffer) > 120_000:
            self.buffer = self.buffer[-80_000:]

    def poll_output(self, timeout_sec: float = 0.4) -> str:
        chunks: list[str] = []
        end = time.time() + timeout_sec
        while time.time() < end:
            rlist, _, _ = select.select([self.master_fd], [], [], 0.08)
            if self.master_fd not in rlist:
                continue
            try:
                data = os.read(self.master_fd, 8192)
            except OSError:
                break
            if not data:
                break
            chunks.append(data.decode("utf-8", errors="ignore"))
        out = "".join(chunks)
        if out:
            self.append_output(out)
        return out

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass
        try:
            os.close(self.master_fd)
        except Exception:
            pass


_SESSIONS: dict[str, ReloginSession] = {}
_LOCK = threading.Lock()
SESSION_TTL_SEC = 20 * 60


def _cleanup_expired() -> None:
    now = datetime.now(timezone.utc)
    dead: list[str] = []
    for sid, sess in _SESSIONS.items():
        age = (now - sess.created_at).total_seconds()
        if age > SESSION_TTL_SEC or sess.proc.poll() is not None:
            dead.append(sid)
    for sid in dead:
        sess = _SESSIONS.pop(sid, None)
        if sess:
            sess.close()


def _claude_auth_status() -> Optional[dict]:
    try:
        proc = _run_claude_cmd(["auth", "status", "--json"], timeout=8, capture_output=True)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    txt = (proc.stdout or "").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


def _read_current_claude_credentials() -> Optional[dict]:
    if not CLAUDE_CREDENTIALS_PATH.exists():
        return None
    try:
        return json.loads(CLAUDE_CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_claude_credentials(payload: dict) -> bool:
    try:
        CLAUDE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_CREDENTIALS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _run_claude_cmd(args: list[str], *, timeout: int = 8, capture_output: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    preexec_fn = None
    user = _claude_runtime_user()
    if user and os.name != "nt" and os.geteuid() == 0:
        try:
            pw = pwd.getpwnam(user)
            env["HOME"] = pw.pw_dir
            env["USER"] = user
            env["LOGNAME"] = user

            def _drop():
                os.initgroups(user, pw.pw_gid)
                os.setgid(pw.pw_gid)
                os.setuid(pw.pw_uid)

            preexec_fn = _drop
        except Exception:
            preexec_fn = None
    kwargs = dict(
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if capture_output:
        kwargs["capture_output"] = True
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if preexec_fn is not None:
        kwargs["preexec_fn"] = preexec_fn
    return subprocess.run([CLAUDE_EXE, *args], **kwargs)


def _reset_claude_runtime() -> None:
    # Stop any running Claude CLI processes so they cannot hold stale auth state.
    try:
        exe_pat = re.escape(str(CLAUDE_EXE))
        subprocess.run(
            ["pkill", "-f", rf"^{exe_pat}(\s|$)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        pass

    # Best-effort logout to clear CLI-managed auth caches.
    try:
        _run_claude_cmd(["auth", "logout"], timeout=8, capture_output=False)
    except Exception:
        pass

    # Remove runtime session folders that can keep prior account context.
    claude_dir = CLAUDE_CREDENTIALS_PATH.parent
    for folder in (claude_dir / "session-env", claude_dir / "sessions"):
        try:
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def _try_switch_noninteractive(account: dict) -> Optional[dict]:
    expected_email = str(account.get("login") or "").strip().lower()
    st0 = _claude_auth_status() or {}
    email0 = str(st0.get("email") or "").strip().lower()
    if st0.get("loggedIn") is True and expected_email and email0 == expected_email:
        limits0 = refresh_limits_for_provider("claude")
        db.set_agent_account_active(int(account["id"]), True)
        db.update_agent_account_limits(
            int(account["id"]),
            status=(limits0 or {}).get("status"),
            percent_5h=(limits0 or {}).get("percent_5h"),
            percent_7d=(limits0 or {}).get("percent_7d"),
            balance_tokens=(limits0 or {}).get("balance_tokens"),
            reset_5h=(limits0 or {}).get("reset_5h"),
            reset_7d=(limits0 or {}).get("reset_7d"),
        )
        return {
            "ok": True,
            "noninteractive": True,
            "account_id": int(account["id"]),
            "message": f"Already logged in as {email0}",
            "limits_updated": bool(limits0),
        }

    creds = account.get("claude_credentials")
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except Exception:
            creds = None
    if not isinstance(creds, dict) or not creds:
        return None
    if not _write_claude_credentials(creds):
        return None
    # Give Claude CLI a short moment to pick up credentials file.
    for _ in range(10):
        st = _claude_auth_status() or {}
        email = str(st.get("email") or "").strip().lower()
        if st.get("loggedIn") is True and (not expected_email or (email and email == expected_email)):
            db.set_agent_account_active(int(account["id"]), True)
            limits = refresh_limits_for_provider("claude")
            db.update_agent_account_limits(
                int(account["id"]),
                status=(limits or {}).get("status"),
                percent_5h=(limits or {}).get("percent_5h"),
                percent_7d=(limits or {}).get("percent_7d"),
                balance_tokens=(limits or {}).get("balance_tokens"),
                reset_5h=(limits or {}).get("reset_5h"),
                reset_7d=(limits or {}).get("reset_7d"),
            )
            return {
                "ok": True,
                "noninteractive": True,
                "account_id": int(account["id"]),
                "message": f"Switched non-interactive to {email or 'unknown'}",
                "limits_updated": bool(limits),
            }
        time.sleep(0.3)
    return None


def start_relogin(account_id: int) -> dict:
    account = db.get_agent_account(account_id)
    if not account:
        raise ValueError("Agent account not found")

    agent_key = str(account.get("agent_shortname") or account.get("agent_name") or "").strip().lower()
    if "claude" not in agent_key:
        raise ValueError("Relogin is implemented only for Claude accounts")
    if int(account.get("status") or 0) == 2:
        raise ValueError("Account is manually disabled (status=2)")
    login_email = str(account.get("login") or "").strip().lower()
    creds = account.get("claude_credentials")
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except Exception:
            creds = None
    if not isinstance(creds, dict) or not creds:
        raise ValueError("Account has no claude_credentials in table")

    _reset_claude_runtime()
    if not _write_claude_credentials(creds):
        raise RuntimeError(f"Failed to write {CLAUDE_CREDENTIALS_PATH}")

    db.set_agent_account_active(account_id, True)
    token = ((creds.get("claudeAiOauth") or {}).get("accessToken") if isinstance(creds, dict) else None)
    if token:
        db.set_agent_account_token(account_id, token)
    limits = refresh_limits_for_provider("claude", token=token or account.get("token"))
    db.update_agent_account_limits(
        account_id,
        status=(limits or {}).get("status"),
        percent_5h=(limits or {}).get("percent_5h"),
        percent_7d=(limits or {}).get("percent_7d"),
        balance_tokens=(limits or {}).get("balance_tokens"),
        reset_5h=(limits or {}).get("reset_5h"),
        reset_7d=(limits or {}).get("reset_7d"),
    )
    st = _claude_auth_status() or {}
    current_email = str(st.get("email") or "").strip().lower()
    if login_email and current_email and current_email != login_email:
        raise RuntimeError(f"Credential switch mismatch: expected={login_email}, current={current_email}")
    msg = f"credentials written for account #{account_id}"
    if login_email:
        msg += f", expected={login_email}"
    if current_email:
        msg += f", current={current_email}"
    return {
        "ok": True,
        "noninteractive": True,
        "account_id": account_id,
        "message": msg,
        "limits_updated": bool(limits),
    }


def cancel_relogin(session_id: str) -> bool:
    with _LOCK:
        sess = _SESSIONS.pop(session_id, None)
    if not sess:
        return False
    sess.close()
    return True


def finish_relogin(session_id: str, code: str, expected_account_id: Optional[int] = None) -> dict:
    code = (code or "").strip()
    with _LOCK:
        _cleanup_expired()
        sess = _SESSIONS.get(session_id)
    if not sess:
        raise ValueError("Relogin session not found or expired")
    if expected_account_id is not None and sess.account_id != int(expected_account_id):
        raise ValueError("Relogin session does not match account")

    if code and sess.proc.poll() is None:
        # Optional backward compatibility if CLI asks for a pasted code.
        raw = code.strip().strip('"').strip("'")
        if "://" in raw or "code=" in raw:
            try:
                m = re.search(r"(?:[?&]|^)code=([^&#]+)", raw)
                if m:
                    raw = unquote(m.group(1)).strip()
            except Exception:
                pass
        raw = raw.replace("\r", "").replace("\n", "").strip()
        if raw:
            try:
                os.write(sess.master_fd, b"\x15")
                os.write(sess.master_fd, raw.encode("utf-8", errors="ignore"))
                os.write(sess.master_fd, b"\r")
                os.write(sess.master_fd, b"\n")
            except OSError:
                pass

    raw_before = sess.buffer
    clean = ""
    ok_line = None
    err_line = None
    last_email = ""
    expected_email = str(sess.expected_login or "").strip().lower()
    started = time.time()
    while time.time() - started < 180:
        try:
            sess.poll_output(timeout_sec=0.35)
        except (OSError, ValueError):
            # PTY may already be closed by CLI; continue with auth-status checks.
            pass
        clean = _strip_ansi(sess.buffer).replace("\r", "\n")
        raw_delta = sess.buffer[len(raw_before) :]
        delta = _strip_ansi(raw_delta).replace("\r", "\n")
        ok_line = _match_line(delta, REL_LOGIN_OK_RE)
        err_line = _match_line(delta, REL_LOGIN_ERR_RE)
        # For device login flow we trust auth status more than noisy CLI text.
        if code and "Pastecodehereifprompted>" in clean.replace(" ", "") and (time.time() - started) > 2.0 and sess.proc.poll() is None:
            try:
                os.write(sess.master_fd, b"\r")
                os.write(sess.master_fd, b"\n")
            except OSError:
                pass
        st = _claude_auth_status() or {}
        current_email = str(st.get("email") or "").strip().lower()
        if current_email:
            last_email = current_email
        if st.get("loggedIn") is True and (not expected_email or (current_email and current_email == expected_email)):
            ok_line = ok_line or f"Logged in as {current_email or 'unknown'}"
            break
        if sess.proc.poll() is not None:
            # CLI may exit before auth status updates globally; keep polling status.
            pass
        time.sleep(0.25)

    rc = sess.proc.poll()

    with _LOCK:
        _SESSIONS.pop(session_id, None)
    sess.close()

    tail = clean[-1200:]
    if err_line and not ok_line:
        low = err_line.lower()
        if "denied" in low or "forbidden" in low:
            raise RuntimeError(f"Relogin failed: {err_line}")
    if not ok_line:
        st = _claude_auth_status() or {}
        current_email = str(st.get("email") or "").strip().lower()
        logged = bool(st.get("loggedIn"))
        if logged and expected_email and current_email and current_email != expected_email:
            raise RuntimeError(f"Relogin went to wrong account: expected={expected_email}, got={current_email}")
        if rc not in (0, None):
            raise RuntimeError(f"Relogin failed (exit={rc})\n{tail}")
    if not ok_line:
        hint = f"expected={expected_email or '-'}, current={last_email or '-'}"
        raise RuntimeError(f"Relogin was not confirmed within timeout ({hint})\n{tail}")

    st = _claude_auth_status() or {}
    logged_in = bool(st.get("loggedIn"))
    current_email = str(st.get("email") or "").strip().lower()
    if not logged_in:
        raise RuntimeError("Relogin failed: Claude reports loggedIn=false after code acceptance")
    if expected_email and current_email and current_email != expected_email:
        raise RuntimeError(
            f"Relogin went to wrong account: expected={expected_email}, got={current_email}"
        )

    account = db.get_agent_account(sess.account_id)
    if not account:
        raise RuntimeError("Agent account not found after relogin")
    db.set_agent_account_active(sess.account_id, True)
    current_creds = _read_current_claude_credentials()
    if current_creds:
        db.set_agent_account_claude_credentials(sess.account_id, current_creds)
        token = ((current_creds.get("claudeAiOauth") or {}).get("accessToken") if isinstance(current_creds, dict) else None)
        if token:
            db.set_agent_account_token(sess.account_id, token)

    limits = refresh_limits_for_provider("claude")
    db.update_agent_account_limits(
        sess.account_id,
        status=(limits or {}).get("status"),
        percent_5h=(limits or {}).get("percent_5h"),
        percent_7d=(limits or {}).get("percent_7d"),
        balance_tokens=(limits or {}).get("balance_tokens"),
        reset_5h=(limits or {}).get("reset_5h"),
        reset_7d=(limits or {}).get("reset_7d"),
    )

    return {
        "ok": True,
        "account_id": sess.account_id,
        "message": ok_line or f"Logged in as {current_email}",
        "limits_updated": bool(limits),
        "output_tail": clean[-1500:],
    }
