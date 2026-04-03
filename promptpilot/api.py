"""FastAPI web API + static file serving."""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import os

from . import db
from .config import get_skills, load_providers, PROJECTS_ROOT
from .models import CostStats, Stats, TaskCreate, TaskInDB, TaskStatus, TaskUpdate
from .version import check_for_update

app = FastAPI(title="PromptPilot", version="0.1.0")

# When frozen by PyInstaller, __file__ points into the temp extraction dir
if getattr(sys, "frozen", False):
    STATIC_DIR = Path(sys._MEIPASS) / "promptpilot" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"


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


@app.get("/api/providers")
def api_providers():
    providers = load_providers()
    default_models = ["sonnet", "opus", "haiku"]
    return {
        name: {
            "description": info.get("description", name),
            "supports_skills": info.get("supports_skills", False),
            "models": info.get("models", default_models if info.get("supports_skills") else []),
        }
        for name, info in providers.items()
    }


@app.get("/api/skills")
def api_skills(provider: Optional[str] = None, workdir: Optional[str] = None):
    """Return available Claude Code skills. Empty list if provider doesn't support skills."""
    if provider is not None:
        providers = load_providers()
        if not providers.get(provider, {}).get("supports_skills", False):
            return []
    return get_skills(working_dir=workdir)


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
                "folder": folder,
                "path": path,
            }
        )
    return entries


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
    try:
        return db.create_agent_account(
            name=str(payload["name"]).strip(),
            shortname=str(payload["shortname"]).strip(),
            agent_id=int(payload["agent_id"]),
            login=(str(payload.get("login")).strip() if payload.get("login") is not None else None),
            password=(str(payload.get("pass")).strip() if payload.get("pass") is not None else None),
            token=(str(payload.get("token")).strip() if payload.get("token") is not None else None),
            login_mode=(str(payload.get("login_mode")).strip() if payload.get("login_mode") is not None else None),
        )
    except Exception as e:
        raise HTTPException(400, f"Create agent account failed: {e}")


@app.patch("/api/admin/agents-accounts/{account_id}")
def api_admin_update_agents_account(account_id: int, payload: dict):
    required = ("name", "shortname", "agent_id")
    if any(str(payload.get(k, "")).strip() == "" for k in required):
        raise HTTPException(400, "name, shortname, agent_id are required")
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


# --- Frontend ---

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
