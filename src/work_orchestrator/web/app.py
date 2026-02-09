"""Web dashboard API for the work orchestrator."""

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from work_orchestrator.config import get_config
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import worktrees as worktrees_mod
from work_orchestrator.db.engine import init_db
from work_orchestrator.web.dashboard import get_dashboard_html


def _get_db():
    config = get_config()
    return init_db(config.db_path)


# ── Handlers ──────────────────────────────────────────────────────────────────


async def index(request: Request):
    return HTMLResponse(get_dashboard_html())


async def api_list_projects(request: Request):
    db = _get_db()
    try:
        projects = projects_mod.list_projects(db)
        return JSONResponse([_project_dict(p) for p in projects])
    finally:
        db.close()


async def api_get_project(request: Request):
    project_id = request.path_params["project_id"]
    db = _get_db()
    try:
        project = projects_mod.get_project(db, project_id)
        if not project:
            return JSONResponse({"error": "Project not found"}, status_code=404)
        return JSONResponse(_project_dict(project))
    finally:
        db.close()


async def api_project_tasks(request: Request):
    project_id = request.path_params["project_id"]
    status_filter = request.query_params.get("status")
    db = _get_db()
    try:
        top_level = tasks_mod.list_tasks(db, project_id, status=status_filter)
        result = []
        for task in top_level:
            td = _full_task_dict(db, task)
            result.append(td)
        return JSONResponse(result)
    finally:
        db.close()


async def api_project_summary(request: Request):
    project_id = request.path_params["project_id"]
    db = _get_db()
    try:
        all_top = tasks_mod.list_tasks(db, project_id)
        all_tasks = list(all_top)
        for t in all_top:
            subs = tasks_mod.list_tasks(db, project_id, parent_task_id=t.id)
            all_tasks.extend(subs)

        counts = {"todo": 0, "in-progress": 0, "done": 0, "blocked": 0}
        for t in all_tasks:
            counts[t.status] = counts.get(t.status, 0) + 1
        total = sum(counts.values())
        progress = (counts["done"] / total * 100) if total > 0 else 0

        return JSONResponse({
            "project_id": project_id,
            "counts": counts,
            "total": total,
            "progress_pct": round(progress, 1),
        })
    finally:
        db.close()


async def api_get_task(request: Request):
    task_id = request.path_params["task_id"]
    db = _get_db()
    try:
        task = tasks_mod.get_task(db, task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        td = _task_dict(task)
        td["events"] = [_event_dict(e) for e in tasks_mod.get_task_events(db, task_id)]
        if task.subtasks:
            td["subtasks"] = [_task_dict(s) for s in task.subtasks]
        return JSONResponse(td)
    finally:
        db.close()


async def api_list_worktrees(request: Request):
    config = get_config()
    db = _get_db()
    try:
        wts = worktrees_mod.list_task_worktrees(db, str(config.repo_path))
        return JSONResponse(wts)
    except Exception:
        return JSONResponse([])
    finally:
        db.close()


# ── Serialization ─────────────────────────────────────────────────────────────


def _project_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "repo_path": p.repo_path,
        "default_branch": p.default_branch,
        "slack_channel": p.slack_channel,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _task_dict(t) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "description": t.description,
        "project_id": t.project_id,
        "parent_task_id": t.parent_task_id,
        "branch_name": t.branch_name,
        "worktree_path": t.worktree_path,
        "pr_url": t.pr_url,
        "depends_on": t.depends_on,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _full_task_dict(db, task) -> dict:
    """Task dict with subtasks nested."""
    td = _task_dict(task)
    subs = tasks_mod.list_tasks(db, task.project_id, parent_task_id=task.id)
    if subs:
        td["subtasks"] = [_task_dict(s) for s in subs]
    return td


def _event_dict(e) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── App ───────────────────────────────────────────────────────────────────────


def create_app() -> Starlette:
    routes = [
        Route("/", index),
        Route("/api/projects", api_list_projects),
        Route("/api/projects/{project_id}", api_get_project),
        Route("/api/projects/{project_id}/tasks", api_project_tasks),
        Route("/api/projects/{project_id}/summary", api_project_summary),
        Route("/api/tasks/{task_id}", api_get_task),
        Route("/api/worktrees", api_list_worktrees),
    ]
    return Starlette(routes=routes)


def run_server(host: str = "127.0.0.1", port: int = 8787):
    app = create_app()
    uvicorn.run(app, host=host, port=port)
