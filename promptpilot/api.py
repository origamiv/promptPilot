"""FastAPI web API + static file serving."""

import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import pyte

from . import db
from .config import APP_TIMEZONE, AGENT_USER, load_providers, PROJECTS_ROOT
from .config import get_provider_env
from .models import CostStats, Stats, TaskCreate, TaskInDB, TaskStatus, TaskUpdate
from . import relogin
from .version import check_for_update

def _get_skills_dir() -> Path:
    """Return ~/.claude/commands for the agent user (AGENT_USER if set, otherwise current user)."""
    if AGENT_USER:
        try:
            pw = pwd.getpwnam(AGENT_USER)
            return Path(pw.pw_dir) / ".claude" / "commands"
        except KeyError:
            pass
    return Path.home() / ".claude" / "commands"


SKILLS_DIR = _get_skills_dir()


def _name_to_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug)
    slug = slug.strip("-")
    return slug or "skill"


def _skill_file_path(slug: str) -> Path:
    return SKILLS_DIR / f"{slug}.md"


def _write_skill_file(slug: str, content: str) -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    _skill_file_path(slug).write_text(content, encoding="utf-8")


def _delete_skill_file(slug: str) -> None:
    path = _skill_file_path(slug)
    if path.exists():
        path.unlink()

app = FastAPI(title="PromptPilot", version="0.1.0")

# When frozen by PyInstaller, __file__ points into the temp extraction dir
if getattr(sys, "frozen", False):
    STATIC_DIR = Path(sys._MEIPASS) / "promptpilot" / "static"
    HELP_DIR = Path(sys.executable).parent / "docs" / "help"
else:
    STATIC_DIR = Path(__file__).parent / "static"
    HELP_DIR = Path(__file__).resolve().parent.parent / "docs" / "help"


_interactive_guard = threading.Lock()
_interactive_session = None
_INTERACTIVE_TERM_COLS = 160
_INTERACTIVE_TERM_ROWS = 40
_INTERACTIVE_TERM_HISTORY = 5000
_DONE_TO_READY_DAYS = 7
_DONE_TO_READY_INTERVAL_SEC = 3600
_done_to_ready_guard = threading.Lock()
_done_to_ready_stop = threading.Event()
_done_to_ready_thread = None


class InteractiveStartRequest(BaseModel):
    provider: str
    working_dir: Optional[str] = None


class InteractiveInputRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    append_newline: bool = True


def _interactive_read_output_locked(session: dict):
    if not session:
        return
    output_path = session.get("output_path")
    if not output_path:
        return

    offset = int(session.get("output_offset") or 0)
    chunks = []
    try:
        with open(output_path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        data = b""

    if data:
        session["output_offset"] = offset + len(data)
        try:
            chunks.append(data.decode("utf-8", errors="replace"))
        except Exception:
            chunks.append(str(data))
    if chunks:
        merged = "".join(chunks)
        session["output"] += merged
        _interactive_feed_pyte_locked(session, merged)


def _interactive_render_pyte_locked(session: dict) -> str:
    screen = session.get("pyte_screen")
    if not screen:
        return ""
    try:
        lines = [line.rstrip() for line in screen.display]
    except Exception:
        return ""
    return "\n".join(lines).rstrip("\n")


def _interactive_feed_pyte_locked(session: dict, text: str):
    if not text:
        return
    stream = session.get("pyte_stream")
    if not stream:
        return
    try:
        stream.feed(text)
    except Exception:
        return
    rendered = _interactive_render_pyte_locked(session)
    if rendered != session.get("rendered", ""):
        session["rendered"] = rendered
        session["render_cursor"] = int(session.get("render_cursor") or 0) + 1


def _interactive_state_locked(session: Optional[dict]) -> dict:
    if not session:
        return {
            "has_session": False,
            "running": False,
        }
    _interactive_read_output_locked(session)
    running = _interactive_is_running_locked(session)
    if not running and session.get("exit_code") is None:
        session["exit_code"] = 0
    return {
        "has_session": True,
        "id": session["id"],
        "provider": session["provider"],
        "working_dir": session["working_dir"],
        "runtime_user": session.get("runtime_user"),
        "running": running,
        "exit_code": session.get("exit_code"),
        "cursor": int(session.get("render_cursor") or 0),
    }


def _interactive_stop_locked(session: Optional[dict]):
    if not session:
        return
    tmux_bin = session.get("tmux_bin") or "tmux"
    tmux_session = session.get("tmux_session")
    if tmux_session:
        try:
            subprocess.run(
                [tmux_bin, "kill-session", "-t", tmux_session],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=session.get("env"),
                preexec_fn=session.get("preexec_fn"),
                close_fds=True,
            )
        except Exception:
            pass
    output_path = session.get("output_path")
    if output_path:
        try:
            os.remove(output_path)
        except OSError:
            pass


def _interactive_cmd_for_provider(provider: str) -> list[str]:
    key = str(provider or "").strip().lower()
    providers = load_providers()
    info = providers.get(key) or providers.get(provider) or {}
    template_parts = shlex.split(str(info.get("cmd") or ""))

    # Prefer canonical interactive commands, but for Claude also respect custom
    # executable path from provider config (e.g. PP_CLAUDE_EXE absolute path).
    candidates = []
    if key in ("claude", "claude-z"):
        candidates.append(template_parts[0] if template_parts else "")
        candidates.append("claude")
    elif key == "codex":
        candidates.append("codex")
    elif key == "qwen":
        candidates.append("qwen")
    elif key == "cursor":
        candidates.append("cursor-agent")
    elif template_parts:
        candidates.append(template_parts[0])

    if not candidates:
        parts = shlex.split(str(provider or ""))
        if parts:
            candidates.append(parts[0])

    resolved: list[str] | None = None
    for cmd0 in candidates:
        if not cmd0:
            continue
        if os.path.isabs(cmd0) or os.sep in cmd0:
            if os.path.exists(cmd0):
                resolved = [cmd0]
                break
            continue
        if shutil.which(cmd0):
            resolved = [cmd0]
            break

    if resolved is None and candidates:
        resolved = [candidates[0]]

    if resolved is None and not template_parts:
        raise ValueError("Invalid provider command")
    if resolved is None:
        resolved = [template_parts[0]]

    # Interactive-only flags requested by project owner.
    if key == "codex":
        if "--yolo" not in resolved:
            resolved.append("--yolo")
    elif key in ("claude", "claude-z"):
        if "--dangerously-skip-permissions" not in resolved:
            resolved.append("--dangerously-skip-permissions")

    return resolved


def _interactive_tmux_target(session: dict) -> str:
    return f"{session['tmux_session']}:0.0"


def _interactive_tmux_exec(session: dict, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [session.get("tmux_bin") or "tmux", *args],
        capture_output=True,
        text=True,
        env=session.get("env"),
        preexec_fn=session.get("preexec_fn"),
        close_fds=True,
    )


def _interactive_is_running_locked(session: Optional[dict]) -> bool:
    if not session:
        return False
    tmux_session = session.get("tmux_session")
    if not tmux_session:
        return False
    try:
        result = _interactive_tmux_exec(session, ["has-session", "-t", tmux_session])
        return result.returncode == 0
    except Exception:
        return False


def _interactive_send_tmux_input_locked(session: dict, text: str):
    target = _interactive_tmux_target(session)

    def _run_send(extra: list[str]):
        res = _interactive_tmux_exec(session, ["send-keys", "-t", target, *extra])
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip() or "tmux send-keys failed"
            raise HTTPException(500, f"Interactive input failed: {err}")

    i = 0
    literal = []

    def _flush_literal():
        if not literal:
            return
        _run_send(["-l", "".join(literal)])
        literal.clear()

    while i < len(text):
        if text.startswith("\x1b[A", i):
            _flush_literal()
            _run_send(["Up"])
            i += 3
            continue
        if text.startswith("\x1b[B", i):
            _flush_literal()
            _run_send(["Down"])
            i += 3
            continue
        if text.startswith("\x1b[C", i):
            _flush_literal()
            _run_send(["Right"])
            i += 3
            continue
        if text.startswith("\x1b[D", i):
            _flush_literal()
            _run_send(["Left"])
            i += 3
            continue
        if text.startswith("\x1b[3~", i):
            _flush_literal()
            _run_send(["Delete"])
            i += 4
            continue
        ch = text[i]
        if ch == "\x03":
            _flush_literal()
            _run_send(["C-c"])
        elif ch in ("\r", "\n"):
            _flush_literal()
            _run_send(["Enter"])
            if ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
                i += 1
        elif ch in ("\x7f", "\b"):
            _flush_literal()
            _run_send(["BSpace"])
        elif ch == "\t":
            _flush_literal()
            _run_send(["Tab"])
        else:
            literal.append(ch)
        i += 1

    _flush_literal()


def _current_system_user() -> str:
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except Exception:
        return str(os.geteuid())


def _interactive_runtime_env(base_env: dict) -> tuple[dict, Optional[object], str, Optional[str]]:
    env = dict(base_env or os.environ)
    runtime_user = _current_system_user()
    runtime_notice = None
    preexec_fn = None

    target_user = (AGENT_USER or "").strip()
    if not target_user or os.name == "nt":
        return env, preexec_fn, runtime_user, runtime_notice

    if os.geteuid() != 0:
        runtime_notice = (
            f"AGENT_USER={target_user} ignored for interactive session "
            f"(server uid={os.geteuid()}, root required for setuid)"
        )
        return env, preexec_fn, runtime_user, runtime_notice

    try:
        pw = pwd.getpwnam(target_user)
    except KeyError:
        raise HTTPException(400, f"Configured AGENT_USER '{target_user}' does not exist")

    env["HOME"] = pw.pw_dir or f"/home/{target_user}"
    env["USER"] = target_user
    env["LOGNAME"] = target_user

    def _drop_privileges():
        os.initgroups(target_user, pw.pw_gid)
        os.setgid(pw.pw_gid)
        os.setuid(pw.pw_uid)

    preexec_fn = _drop_privileges
    runtime_user = target_user
    return env, preexec_fn, runtime_user, runtime_notice


def _run_done_to_ready_once():
    try:
        moved = db.move_completed_done_to_ready(before_days=_DONE_TO_READY_DAYS)
        if moved:
            print(f"[cron] moved {moved} task(s) to ref status 'ready'")
    except Exception as e:
        print(f"[cron] move completed->ready failed: {e}")


def _done_to_ready_loop():
    while not _done_to_ready_stop.wait(_DONE_TO_READY_INTERVAL_SEC):
        _run_done_to_ready_once()


@app.on_event("startup")
def _startup_done_to_ready_cron():
    global _done_to_ready_thread
    with _done_to_ready_guard:
        if _done_to_ready_thread and _done_to_ready_thread.is_alive():
            return
        _done_to_ready_stop.clear()
        _run_done_to_ready_once()
        _done_to_ready_thread = threading.Thread(target=_done_to_ready_loop, name="done-to-ready-cron", daemon=True)
        _done_to_ready_thread.start()


@app.on_event("shutdown")
def _shutdown_done_to_ready_cron():
    global _done_to_ready_thread
    with _done_to_ready_guard:
        _done_to_ready_stop.set()
        _done_to_ready_thread = None


# --- API ---

@app.get("/api/tasks", response_model=list[TaskInDB])
def api_list_tasks(status: Optional[TaskStatus] = None, limit: int = 50, offset: int = 0):
    return db.list_tasks(status=status, limit=limit, offset=offset)


@app.post("/api/tasks", response_model=TaskInDB, status_code=201)
def api_create_task(task: TaskCreate):
    return db.create_task(task)


@app.get("/api/tasks/{task_id}", response_model=TaskInDB)
def api_get_task(task_id: int):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.patch("/api/tasks/{task_id}", response_model=dict)
def api_update_task(task_id: int, update: TaskUpdate):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if update.status == TaskStatus.CANCELLED:
        if not db.cancel_task(task_id):
            raise HTTPException(400, "Can only cancel pending or rate_limited tasks")

    if update.priority is not None:
        if not db.update_priority(task_id, update.priority):
            raise HTTPException(400, "Can only reprioritize pending or rate_limited tasks")

    if update.task_status_id is not None:
        if not db.update_task_status_id(task_id, update.task_status_id):
            raise HTTPException(404, "Task not found")

    if update.questions is not None:
        if not db.update_task_questions(task_id, update.questions):
            raise HTTPException(404, "Task not found")

    if update.nom_run is not None:
        if not db.update_task_nom_run(task_id, update.nom_run):
            raise HTTPException(404, "Task not found")

    return {"ok": True}


@app.delete("/api/tasks/{task_id}", response_model=dict)
def api_delete_task(task_id: int):
    if not db.delete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/reset", response_model=dict)
def api_reset_task(task_id: int):
    if not db.reset_task(task_id):
        raise HTTPException(400, "Task not found or not in running state")
    return {"ok": True}


@app.get("/api/stats", response_model=Stats)
def api_stats():
    return db.get_stats()


@app.get("/api/stats/costs", response_model=CostStats)
def api_cost_stats():
    return db.get_cost_stats()


@app.get("/api/worker/status")
def api_worker_status():
    return {"paused": db.is_paused()}


@app.post("/api/worker/pause")
def api_worker_pause():
    db.set_setting("worker_paused", "1")
    return {"ok": True, "paused": True}


@app.post("/api/worker/resume")
def api_worker_resume():
    db.set_setting("worker_paused", "0")
    return {"ok": True, "paused": False}


@app.get("/api/version")
def api_version():
    return check_for_update()


@app.get("/api/config")
def api_config():
    return {"timezone": APP_TIMEZONE}


@app.get("/api/providers")
def api_providers():
    providers = load_providers()
    agents = db.list_active_agents(limit=500)
    default_models = ["sonnet", "opus", "haiku"]
    items = {}
    for agent in agents:
        shortname = str(agent.get("shortname") or "").strip()
        if not shortname:
            continue
        info = providers.get(shortname, {})
        supports_skills = bool(info.get("supports_skills", False))
        models = info.get("models")
        if models is None:
            models = default_models if supports_skills else []
        items[shortname] = {
            "description": agent.get("name") or info.get("description", shortname),
            "supports_skills": supports_skills,
            "models": models,
        }
    return items


@app.get("/api/skills")
def api_skills(provider: Optional[str] = None, workdir: Optional[str] = None):
    """Return active skills for a provider from DB. Empty list if provider doesn't support skills."""
    if provider is not None:
        providers = load_providers()
        if not providers.get(provider, {}).get("supports_skills", False):
            return []
        rows = db.list_skills_for_provider(provider)
    else:
        rows = db.list_skills_for_provider("")
    return [
        {
            "name": r["name"],
            "description": r.get("description"),
            "argument_hint": r.get("argument_hint"),
            "source": "db",
        }
        for r in rows
    ]


@app.get("/api/admin/skills/agents")
def api_admin_skills_agents():
    providers = load_providers()
    agents = db.list_active_agents(limit=500)
    rows = []
    for agent in agents:
        shortname = str(agent.get("shortname") or "").strip()
        if not shortname:
            continue
        info = providers.get(shortname, {})
        if not info.get("supports_skills", False):
            continue
        rows.append(
            {
                "shortname": shortname,
                "name": agent.get("name") or info.get("description") or shortname,
                "supports_skills": True,
            }
        )
    return rows


@app.get("/api/admin/skills")
def api_admin_skills_list(
    page: int = 1,
    page_size: int = 50,
    q: Optional[str] = None,
    agent: Optional[str] = None,
    active_only: bool = False,
):
    result = db.list_skills(page=page, page_size=page_size, q=q or None, agent=agent or None, active_only=active_only)
    items = result["items"]
    for item in items:
        if "agents" in item and isinstance(item["agents"], str):
            try:
                item["agents"] = json.loads(item["agents"])
            except Exception:
                item["agents"] = []
    return result


@app.post("/api/admin/skills")
def api_admin_skills_create(payload: dict):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    slug = str(payload.get("slug") or "").strip() or _name_to_slug(name)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise HTTPException(400, f"Invalid slug: {slug!r}. Only lowercase letters, digits, hyphens and underscores.")
    description = payload.get("description") or None
    content = str(payload.get("content") or "")
    argument_hint = payload.get("argument_hint") or None
    agents = payload.get("agents") or []
    if not isinstance(agents, list):
        agents = []
    is_active = bool(payload.get("is_active", True))
    try:
        row = db.create_skill(name, slug, description, content, argument_hint, agents, is_active)
    except Exception as e:
        msg = str(e)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(400, "Skill with this name or slug already exists")
        raise HTTPException(400, f"Create failed: {msg}")
    try:
        _write_skill_file(slug, content)
    except Exception:
        pass
    if row and isinstance(row.get("agents"), str):
        try:
            row["agents"] = json.loads(row["agents"])
        except Exception:
            row["agents"] = []
    return row


@app.get("/api/admin/skills/{skill_id}")
def api_admin_skills_get(skill_id: int):
    row = db.get_skill(skill_id)
    if not row:
        raise HTTPException(404, "Skill not found")
    if isinstance(row.get("agents"), str):
        try:
            row["agents"] = json.loads(row["agents"])
        except Exception:
            row["agents"] = []
    return row


@app.put("/api/admin/skills/{skill_id}")
def api_admin_skills_update(skill_id: int, payload: dict):
    existing = db.get_skill(skill_id)
    if not existing:
        raise HTTPException(404, "Skill not found")
    old_slug = existing["slug"]
    name = str(payload.get("name") or existing["name"]).strip()
    slug = str(payload.get("slug") or existing["slug"]).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise HTTPException(400, f"Invalid slug: {slug!r}")
    description = payload.get("description", existing.get("description"))
    if description is not None:
        description = description or None
    content = str(payload.get("content", existing.get("content", "")))
    argument_hint = payload.get("argument_hint", existing.get("argument_hint")) or None
    agents = payload.get("agents", existing.get("agents") or [])
    if not isinstance(agents, list):
        agents = []
    is_active = bool(payload.get("is_active", existing.get("is_active", True)))
    try:
        row = db.update_skill(skill_id, name, slug, description, content, argument_hint, agents, is_active)
    except Exception as e:
        msg = str(e)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise HTTPException(400, "Skill with this name or slug already exists")
        raise HTTPException(400, f"Update failed: {msg}")
    if not row:
        raise HTTPException(404, "Skill not found")
    try:
        if old_slug != slug:
            _delete_skill_file(old_slug)
        _write_skill_file(slug, content)
    except Exception:
        pass
    if isinstance(row.get("agents"), str):
        try:
            row["agents"] = json.loads(row["agents"])
        except Exception:
            row["agents"] = []
    return row


@app.patch("/api/admin/skills/{skill_id}/toggle")
def api_admin_skills_toggle(skill_id: int, payload: dict = None):
    is_active = None
    if payload:
        raw = payload.get("is_active")
        if raw is not None:
            is_active = bool(raw)
    row = db.toggle_skill(skill_id, is_active)
    if not row:
        raise HTTPException(404, "Skill not found")
    return row


@app.delete("/api/admin/skills/{skill_id}")
def api_admin_skills_delete(skill_id: int):
    slug = db.delete_skill(skill_id)
    if slug is None:
        raise HTTPException(404, "Skill not found")
    try:
        _delete_skill_file(slug)
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/projects")
def api_projects(q: Optional[str] = None):
    """Return list of projects from DB table {schema}.projects."""
    rows = db.list_projects(search=q, limit=400)
    base_root = PROJECTS_ROOT or "/www/wwwroot"
    entries = []
    for r in rows:
        folder = (r.get("folder") or "").strip()
        if not folder:
            continue
        path = folder if os.path.isabs(folder) else os.path.join(base_root, folder)
        entries.append(
            {
                "id": r.get("id"),
                "name": r.get("name") or folder,
                "shortname": r.get("shortname"),
                "folder": folder,
                "path": path,
                "color": r.get("color"),
                "comment": r.get("comment"),
            }
        )
    return entries


@app.get("/api/interactive/state")
def api_interactive_state():
    with _interactive_guard:
        return _interactive_state_locked(_interactive_session)


@app.post("/api/interactive/start")
def api_interactive_start(payload: InteractiveStartRequest):
    provider = str(payload.provider or "").strip()
    if not provider:
        raise HTTPException(400, "provider is required")

    working_dir = (payload.working_dir or "").strip() or None
    if working_dir and not os.path.isdir(working_dir):
        raise HTTPException(400, f"Working directory does not exist: {working_dir}")

    with _interactive_guard:
        global _interactive_session
        if _interactive_session and _interactive_is_running_locked(_interactive_session):
            raise HTTPException(409, "Interactive session already running")
        if _interactive_session:
            _interactive_stop_locked(_interactive_session)

        cmd = _interactive_cmd_for_provider(provider)
        env, preexec_fn, runtime_user, runtime_notice = _interactive_runtime_env(get_provider_env(provider))
        tmux_bin = shutil.which("tmux")
        if not tmux_bin:
            raise HTTPException(500, "tmux is required for interactive sessions")

        tmux_session = f"pp_interactive_{uuid.uuid4().hex[:12]}"
        output_path = os.path.join(tempfile.gettempdir(), f"{tmux_session}.log")
        touch_cmd = f": > {shlex.quote(output_path)}"
        touched = subprocess.run(
            ["/bin/sh", "-lc", touch_cmd],
            capture_output=True,
            text=True,
            env=env,
            preexec_fn=preexec_fn,
            close_fds=True,
        )
        if touched.returncode != 0:
            err = (touched.stderr or touched.stdout or "").strip()
            raise HTTPException(500, f"Interactive start failed: cannot create log file: {err or 'touch failed'}")

        pane_cmd = f"exec {shlex.quote(cmd[0])}"
        start_args = [tmux_bin, "new-session", "-d", "-s", tmux_session]
        if working_dir:
            start_args += ["-c", working_dir]
        start_args.append(pane_cmd)

        try:
            started = subprocess.run(
                start_args,
                capture_output=True,
                text=True,
                env=env,
                preexec_fn=preexec_fn,
                close_fds=True,
            )
        except FileNotFoundError:
            raise HTTPException(500, "tmux is not available in runtime PATH")
        except Exception as e:
            raise HTTPException(500, f"Interactive start failed: {e}")

        if started.returncode != 0:
            try:
                os.remove(output_path)
            except OSError:
                pass
            err = (started.stderr or started.stdout or "").strip()
            raise HTTPException(500, f"Interactive start failed: {err or 'tmux new-session failed'}")

        pipe_cmd = f"cat >> {shlex.quote(output_path)}"
        pipe_res = subprocess.run(
            [tmux_bin, "pipe-pane", "-o", "-t", f"{tmux_session}:0.0", pipe_cmd],
            capture_output=True,
            text=True,
            env=env,
            preexec_fn=preexec_fn,
            close_fds=True,
        )
        if pipe_res.returncode != 0:
            subprocess.run(
                [tmux_bin, "kill-session", "-t", tmux_session],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                preexec_fn=preexec_fn,
                close_fds=True,
            )
            try:
                os.remove(output_path)
            except OSError:
                pass
            err = (pipe_res.stderr or pipe_res.stdout or "").strip()
            raise HTTPException(500, f"Interactive start failed: {err or 'tmux pipe-pane failed'}")

        _interactive_session = {
            "id": str(uuid.uuid4()),
            "provider": provider,
            "working_dir": working_dir,
            "runtime_user": runtime_user,
            "tmux_bin": tmux_bin,
            "tmux_session": tmux_session,
            "output_path": output_path,
            "output_offset": 0,
            "env": env,
            "preexec_fn": preexec_fn,
            "output": "",
            "pyte_screen": pyte.HistoryScreen(_INTERACTIVE_TERM_COLS, _INTERACTIVE_TERM_ROWS, history=_INTERACTIVE_TERM_HISTORY),
            "pyte_stream": None,
            "rendered": "",
            "render_cursor": 0,
            "exit_code": None,
        }
        _interactive_session["pyte_stream"] = pyte.Stream(_interactive_session["pyte_screen"])
        if runtime_notice:
            notice = f"[system] {runtime_notice}\n"
            _interactive_session["output"] = notice
            _interactive_feed_pyte_locked(_interactive_session, notice)
        return _interactive_state_locked(_interactive_session)


@app.post("/api/interactive/input")
def api_interactive_input(payload: InteractiveInputRequest):
    with _interactive_guard:
        session = _interactive_session
        if not session:
            raise HTTPException(404, "Interactive session not found")
        if not _interactive_is_running_locked(session):
            _interactive_read_output_locked(session)
            if session.get("exit_code") is None:
                session["exit_code"] = 0
            raise HTTPException(400, "Interactive session already stopped")
        data = payload.text + ("\n" if payload.append_newline else "")
        _interactive_send_tmux_input_locked(session, data)
        _interactive_read_output_locked(session)
        return {"ok": True, "cursor": int(session.get("render_cursor") or 0)}


@app.get("/api/interactive/output")
def api_interactive_output(cursor: int = 0):
    with _interactive_guard:
        session = _interactive_session
        if not session:
            return {
                "has_session": False,
                "running": False,
                "cursor": 0,
                "chunk": "",
            }
        _interactive_read_output_locked(session)
        rendered = session.get("rendered", "")
        running = _interactive_is_running_locked(session)
        if not running and session.get("exit_code") is None:
            session["exit_code"] = 0
        current_cursor = int(session.get("render_cursor") or 0)
        safe_cursor = max(0, min(int(cursor), current_cursor))
        chunk = rendered if safe_cursor != current_cursor else ""
        return {
            "has_session": True,
            "running": running,
            "exit_code": session.get("exit_code"),
            "cursor": current_cursor,
            "chunk": chunk,
            "screen": rendered,
            "provider": session["provider"],
            "working_dir": session["working_dir"],
            "runtime_user": session.get("runtime_user"),
            "id": session["id"],
        }


@app.post("/api/interactive/stop")
def api_interactive_stop():
    with _interactive_guard:
        global _interactive_session
        if not _interactive_session:
            return {"ok": True, "running": False}
        _interactive_stop_locked(_interactive_session)
        _interactive_session = None
        return {"ok": True, "running": False}


@app.get("/api/admin/projects")
def api_admin_projects(q: Optional[str] = None):
    return db.list_projects_admin(search=q, limit=500)


@app.post("/api/admin/projects")
def api_admin_create_project(payload: dict):
    required = ("name", "shortname", "folder")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name, shortname, folder are required")
    try:
        row = db.create_project(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            folder=str(payload["folder"]).strip(),
            color=(str(payload.get("color")).strip() if payload.get("color") is not None else None),
            comment=(str(payload.get("comment")).strip() if payload.get("comment") is not None else None),
        )
        return row
    except Exception as e:
        raise HTTPException(400, f"Create project failed: {e}")


@app.patch("/api/admin/projects/{project_id}")
def api_admin_update_project(project_id: int, payload: dict):
    required = ("name", "shortname", "folder")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name, shortname, folder are required")
    try:
        ok = db.update_project(
            project_id=project_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            folder=str(payload["folder"]).strip(),
            color=(str(payload.get("color")).strip() if payload.get("color") is not None else None),
            comment=(str(payload.get("comment")).strip() if payload.get("comment") is not None else None),
        )
        if not ok:
            raise HTTPException(404, "Project not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update project failed: {e}")


@app.delete("/api/admin/projects/{project_id}")
def api_admin_delete_project(project_id: int):
    try:
        ok = db.delete_project(project_id)
        if not ok:
            raise HTTPException(404, "Project not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete project failed: {e}")


@app.get("/api/admin/agents")
def api_admin_agents(q: Optional[str] = None):
    return db.list_agents(search=q, limit=500)


@app.post("/api/admin/agents")
def api_admin_create_agent(payload: dict):
    required = ("name", "shortname")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name and shortname are required")
    try:
        return db.create_agent(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            email=(str(payload.get("email")).strip() if payload.get("email") is not None else None),
            priority=int(payload.get("priority", 0) or 0),
            status=int(payload.get("status", 1) or 1),
            color=(str(payload.get("color")).strip() if payload.get("color") is not None else None),
            avatar_url=(str(payload.get("avatar_url")).strip() if payload.get("avatar_url") is not None else None),
        )
    except Exception as e:
        raise HTTPException(400, f"Create agent failed: {e}")


@app.patch("/api/admin/agents/{agent_id}")
def api_admin_update_agent(agent_id: int, payload: dict):
    required = ("name", "shortname")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name and shortname are required")
    try:
        ok = db.update_agent(
            agent_id=agent_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            email=(str(payload.get("email")).strip() if payload.get("email") is not None else None),
            priority=int(payload.get("priority", 0) or 0),
            status=int(payload.get("status", 1) or 1),
            color=(str(payload.get("color")).strip() if payload.get("color") is not None else None),
            avatar_url=(str(payload.get("avatar_url")).strip() if payload.get("avatar_url") is not None else None),
        )
        if not ok:
            raise HTTPException(404, "Agent not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update agent failed: {e}")


@app.delete("/api/admin/agents/{agent_id}")
def api_admin_delete_agent(agent_id: int):
    try:
        ok = db.delete_agent(agent_id)
        if not ok:
            raise HTTPException(404, "Agent not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete agent failed: {e}")


@app.get("/api/admin/agents-accounts")
def api_admin_agents_accounts(q: Optional[str] = None):
    return db.list_agents_accounts(search=q, limit=500)


@app.post("/api/admin/agents-accounts")
def api_admin_create_agents_account(payload: dict):
    required = ("name", "shortname", "agent_id")
    if any(str(payload.get(k, "")).strip() == "" for k in required):
        raise HTTPException(400, "name, shortname, agent_id are required")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be integer 0..3")
    if status not in (0, 1, 2, 3):
        raise HTTPException(400, "status must be integer 0..3")
    is_active = bool(payload.get("is_active", False))
    try:
        return db.create_agent_account(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            agent_id=int(payload["agent_id"]),
            login=(str(payload.get("login")).strip() if payload.get("login") is not None else None),
            password=(str(payload.get("pass")).strip() if payload.get("pass") is not None else None),
            token=(str(payload.get("token")).strip() if payload.get("token") is not None else None),
            login_mode=(str(payload.get("login_mode")).strip() if payload.get("login_mode") is not None else None),
            status=status,
            is_active=is_active,
        )
    except Exception as e:
        raise HTTPException(400, f"Create agent account failed: {e}")


@app.patch("/api/admin/agents-accounts/{account_id}")
def api_admin_update_agents_account(account_id: int, payload: dict):
    required = ("name", "shortname", "agent_id")
    if any(str(payload.get(k, "")).strip() == "" for k in required):
        raise HTTPException(400, "name, shortname, agent_id are required")
    status = payload.get("status")
    if status is not None:
        try:
            status = int(status)
        except Exception:
            raise HTTPException(400, "status must be integer 0..3")
        if status not in (0, 1, 2, 3):
            raise HTTPException(400, "status must be integer 0..3")
    is_active = payload.get("is_active")
    if is_active is not None:
        is_active = bool(is_active)
    try:
        ok = db.update_agent_account(
            account_id=account_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            agent_id=int(payload["agent_id"]),
            login=(str(payload.get("login")).strip() if payload.get("login") is not None else None),
            password=(str(payload.get("pass")).strip() if payload.get("pass") is not None else None),
            token=(str(payload.get("token")).strip() if payload.get("token") is not None else None),
            login_mode=(str(payload.get("login_mode")).strip() if payload.get("login_mode") is not None else None),
            status=status,
            is_active=is_active,
        )
        if not ok:
            raise HTTPException(404, "Agent account not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update agent account failed: {e}")


@app.delete("/api/admin/agents-accounts/{account_id}")
def api_admin_delete_agents_account(account_id: int):
    try:
        ok = db.delete_agent_account(account_id)
        if not ok:
            raise HTTPException(404, "Agent account not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete agent account failed: {e}")


@app.post("/api/admin/agents-accounts/{account_id}/relogin/start")
def api_admin_start_relogin(account_id: int):
    try:
        return relogin.start_relogin(account_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Relogin start failed: {e}")


@app.post("/api/admin/agents-accounts/{account_id}/relogin/finish")
def api_admin_finish_relogin(account_id: int, payload: dict):
    session_id = str(payload.get("session_id") or "").strip()
    code = str(payload.get("code") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id is required")
    account = db.get_agent_account(account_id)
    if not account:
        raise HTTPException(404, "Agent account not found")
    try:
        return relogin.finish_relogin(session_id=session_id, code=code, expected_account_id=account_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Relogin finish failed: {e}")


@app.post("/api/admin/agents-accounts/{account_id}/relogin/cancel")
def api_admin_cancel_relogin(account_id: int, payload: dict):
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id is required")
    ok = relogin.cancel_relogin(session_id)
    return {"ok": ok}


@app.get("/api/admin/prompts")
def api_admin_prompts(q: Optional[str] = None):
    return db.list_prompts(search=q, limit=500)


@app.post("/api/admin/prompts")
def api_admin_create_prompt(payload: dict):
    required = ("name", "shortname", "message")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name, shortname, message are required")
    options = payload.get("options")
    if options is not None and not isinstance(options, dict):
        raise HTTPException(400, "options must be an object or null")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be integer 0..3")
    if status not in (0, 1, 2, 3):
        raise HTTPException(400, "status must be integer 0..3")
    try:
        return db.create_prompt(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            message=str(payload["message"]).strip(),
            options=options,
            status=status,
        )
    except Exception as e:
        raise HTTPException(400, f"Create prompt failed: {e}")


@app.patch("/api/admin/prompts/{prompt_id}")
def api_admin_update_prompt(prompt_id: int, payload: dict):
    required = ("name", "shortname", "message")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name, shortname, message are required")
    options = payload.get("options")
    if options is not None and not isinstance(options, dict):
        raise HTTPException(400, "options must be an object or null")
    status = payload.get("status")
    if status is not None:
        try:
            status = int(status)
        except Exception:
            raise HTTPException(400, "status must be integer 0..3")
        if status not in (0, 1, 2, 3):
            raise HTTPException(400, "status must be integer 0..3")
    try:
        ok = db.update_prompt(
            prompt_id=prompt_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            message=str(payload["message"]).strip(),
            options=options,
            status=status,
        )
        if not ok:
            raise HTTPException(404, "Prompt not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update prompt failed: {e}")


@app.delete("/api/admin/prompts/{prompt_id}")
def api_admin_delete_prompt(prompt_id: int):
    try:
        ok = db.delete_prompt(prompt_id)
        if not ok:
            raise HTTPException(404, "Prompt not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete prompt failed: {e}")


@app.get("/api/admin/workers")
def api_admin_workers(q: Optional[str] = None):
    return db.list_workers(search=q, limit=500)


@app.post("/api/admin/workers")
def api_admin_create_worker(payload: dict):
    required = ("name", "shortname")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name and shortname are required")
    status = payload.get("status", 0)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be integer 0..3")
    if status not in (0, 1, 2, 3):
        raise HTTPException(400, "status must be integer 0..3")
    agent_id = payload.get("agent_id")
    avatar_url = payload.get("avatar_url")
    prompt = payload.get("prompt")
    try:
        return db.create_worker(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            role=(str(payload.get("role")).strip() if payload.get("role") is not None else None),
            is_agent=bool(payload.get("is_agent", False)),
            agent_id=int(agent_id) if agent_id else None,
            status=status,
            avatar_url=str(avatar_url).strip() if avatar_url else None,
            prompt=str(prompt).strip() if prompt else None,
        )
    except Exception as e:
        raise HTTPException(400, f"Create worker failed: {e}")


@app.patch("/api/admin/workers/{worker_id}")
def api_admin_update_worker(worker_id: int, payload: dict):
    required = ("name", "shortname")
    if any(not str(payload.get(k, "")).strip() for k in required):
        raise HTTPException(400, "name and shortname are required")
    status = payload.get("status", 0)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be integer 0..3")
    if status not in (0, 1, 2, 3):
        raise HTTPException(400, "status must be integer 0..3")
    agent_id = payload.get("agent_id")
    avatar_url = payload.get("avatar_url")
    prompt = payload.get("prompt")
    try:
        ok = db.update_worker(
            worker_id=worker_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            role=(str(payload.get("role")).strip() if payload.get("role") is not None else None),
            is_agent=bool(payload.get("is_agent", False)),
            agent_id=int(agent_id) if agent_id else None,
            status=status,
            avatar_url=str(avatar_url).strip() if avatar_url else None,
            prompt=str(prompt).strip() if prompt else None,
        )
        if not ok:
            raise HTTPException(404, "Worker not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update worker failed: {e}")


@app.delete("/api/admin/workers/{worker_id}")
def api_admin_delete_worker(worker_id: int):
    try:
        ok = db.delete_worker(worker_id)
        if not ok:
            raise HTTPException(404, "Worker not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete worker failed: {e}")


# --- Task Statuses ---

@app.get("/api/admin/task-statuses")
def api_admin_task_statuses(q: Optional[str] = None):
    return db.list_task_statuses(search=q, limit=500)


@app.post("/api/admin/task-statuses")
def api_admin_create_task_status(payload: dict):
    if not str(payload.get("name", "")).strip():
        raise HTTPException(400, "name is required")
    if not str(payload.get("shortname", "")).strip():
        raise HTTPException(400, "shortname is required")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be 0, 1 or 2")
    if status not in (0, 1, 2):
        raise HTTPException(400, "status must be 0, 1 or 2")
    nom = payload.get("nom")
    nom = int(nom) if nom is not None and str(nom).strip() else None
    try:
        return db.create_task_status(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            status_to=str(payload["status_to"]).strip() if payload.get("status_to") else None,
            color=str(payload["color"]).strip() if payload.get("color") else None,
            status=status,
            nom=nom,
        )
    except Exception as e:
        raise HTTPException(400, f"Create task status failed: {e}")


@app.patch("/api/admin/task-statuses/{status_id}")
def api_admin_update_task_status(status_id: int, payload: dict):
    if not str(payload.get("name", "")).strip():
        raise HTTPException(400, "name is required")
    if not str(payload.get("shortname", "")).strip():
        raise HTTPException(400, "shortname is required")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be 0, 1 or 2")
    if status not in (0, 1, 2):
        raise HTTPException(400, "status must be 0, 1 or 2")
    nom = payload.get("nom")
    nom = int(nom) if nom is not None and str(nom).strip() else None
    try:
        ok = db.update_task_status(
            status_id=status_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            status_to=str(payload["status_to"]).strip() if payload.get("status_to") else None,
            color=str(payload["color"]).strip() if payload.get("color") else None,
            status=status,
            nom=nom,
        )
        if not ok:
            raise HTTPException(404, "Task status not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update task status failed: {e}")


@app.delete("/api/admin/task-statuses/{status_id}")
def api_admin_delete_task_status(status_id: int):
    try:
        ok = db.delete_task_status(status_id)
        if not ok:
            raise HTTPException(404, "Task status not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete task status failed: {e}")


# --- Priorities ---

@app.get("/api/admin/priorities")
def api_admin_priorities(q: Optional[str] = None):
    return db.list_priorities(search=q, limit=500)


@app.post("/api/admin/priorities")
def api_admin_create_priority(payload: dict):
    if not str(payload.get("name", "")).strip():
        raise HTTPException(400, "name is required")
    if not str(payload.get("shortname", "")).strip():
        raise HTTPException(400, "shortname is required")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be 0, 1 or 2")
    if status not in (0, 1, 2):
        raise HTTPException(400, "status must be 0, 1 or 2")
    try:
        return db.create_priority(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            icon=str(payload["icon"]).strip() if payload.get("icon") else None,
            status=status,
        )
    except Exception as e:
        raise HTTPException(400, f"Create priority failed: {e}")


@app.patch("/api/admin/priorities/{priority_id}")
def api_admin_update_priority(priority_id: int, payload: dict):
    if not str(payload.get("name", "")).strip():
        raise HTTPException(400, "name is required")
    if not str(payload.get("shortname", "")).strip():
        raise HTTPException(400, "shortname is required")
    status = payload.get("status", 1)
    try:
        status = int(status)
    except Exception:
        raise HTTPException(400, "status must be 0, 1 or 2")
    if status not in (0, 1, 2):
        raise HTTPException(400, "status must be 0, 1 or 2")
    try:
        ok = db.update_priority(
            priority_id=priority_id,
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            icon=str(payload["icon"]).strip() if payload.get("icon") else None,
            status=status,
        )
        if not ok:
            raise HTTPException(404, "Priority not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Update priority failed: {e}")


@app.delete("/api/admin/priorities/{priority_id}")
def api_admin_delete_priority(priority_id: int):
    try:
        ok = db.delete_priority(priority_id)
        if not ok:
            raise HTTPException(404, "Priority not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Delete priority failed: {e}")


# --- Frontend ---

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers=_SPA_HEADERS)


_SPA_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/help/{section}")
def help_page(section: str):
    allowed = {
        "tasks": "tasks.html",
        "interactive": "interactive.html",
        "agents": "agents.html",
        "accounts": "accounts.html",
        "projects": "projects.html",
        "prompts": "prompts.html",
        "skills": "skills.html",
        "workers": "workers.html",
        "task-statuses": "task-statuses.html",
        "priorities": "priorities.html",
        "kanban": "kanban.html",
    }
    name = allowed.get(str(section or "").strip().lower())
    if not name:
        raise HTTPException(404, "Help page not found")
    path = HELP_DIR / name
    if not path.exists():
        raise HTTPException(404, "Help page not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/images/{file_path:path}")
def serve_static_image(file_path: str):
    path = (STATIC_DIR / "images" / file_path).resolve()
    if not str(path).startswith(str((STATIC_DIR / "images").resolve())) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve index.html for all non-API paths so History API routing works on F5."""
    return FileResponse(STATIC_DIR / "index.html", headers=_SPA_HEADERS)
