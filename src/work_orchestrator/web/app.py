"""Web dashboard API for the work orchestrator."""

import asyncio
import json
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from work_orchestrator.config import get_config
from work_orchestrator.core import agents as agents_mod
from work_orchestrator.core import events as events_mod
from work_orchestrator.core import planner as planner_mod
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import worktrees as worktrees_mod
from work_orchestrator.db.engine import init_db


# Path to the built frontend
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


def _get_db():
    config = get_config()
    return init_db(config.db_path)


# ── Handlers ──────────────────────────────────────────────────────────────────


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

        counts = {"todo": 0, "in-progress": 0, "done": 0, "blocked": 0, "review": 0}
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


async def api_dispatch_task(request: Request):
    """Dispatch a task to an agent. Auto-picks slot, assigns, and launches."""
    task_id = request.path_params["task_id"]
    body = await request.json()
    backend = body.get("backend")
    model = body.get("model")
    max_turns = body.get("max_turns")

    config = get_config()
    db = _get_db()
    try:
        task = tasks_mod.get_task(db, task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)

        output_dir = str(Path(config.agent_output_dir).resolve())

        run = agents_mod.delegate_task(
            db,
            task_id=task_id,
            instructions=f"Complete the task: {task.title}",
            output_dir=output_dir,
            project_id=task.project_id,
            model=model or config.agent_default_model,
            max_turns=max_turns or config.agent_default_max_turns,
            backend=backend or config.default_backend,
        )
        return JSONResponse(_agent_run_dict(run))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
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
        "priority": t.priority,
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


# ── Planning Handlers ────────────────────────────────────────────────────────


async def api_plan_start(request: Request):
    body = await request.json()
    title = body.get("title", "New chat")
    project_id = body.get("project_id")
    db = _get_db()
    try:
        session = planner_mod.create_session(db, title, project_id=project_id)
        return JSONResponse(_session_dict(session))
    finally:
        db.close()


async def api_plan_update(request: Request):
    """Update session metadata (title, project_id)."""
    session_id = request.path_params["session_id"]
    body = await request.json()
    db = _get_db()
    try:
        session = planner_mod.get_session(db, session_id)
        if not session:
            return JSONResponse({"error": "Session not found"}, status_code=404)
        if "title" in body:
            planner_mod.update_session_title(db, session_id, body["title"])
        if "project_id" in body:
            planner_mod.update_session_project(db, session_id, body["project_id"])
        session = planner_mod.get_session(db, session_id)
        return JSONResponse(_session_dict(session))
    finally:
        db.close()


async def api_plan_sessions(request: Request):
    project_id = request.query_params.get("project_id")
    db = _get_db()
    try:
        sessions = planner_mod.list_sessions(db, project_id=project_id)
        return JSONResponse([_session_dict(s) for s in sessions])
    finally:
        db.close()


async def api_plan_detail(request: Request):
    session_id = request.path_params["session_id"]
    db = _get_db()
    try:
        session = planner_mod.get_session(db, session_id)
        if not session:
            return JSONResponse({"error": "Session not found"}, status_code=404)
        messages = planner_mod.get_messages(db, session_id)
        result = _session_dict(session)
        result["messages"] = [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in messages
        ]
        if session.prd_content:
            result["prd_content"] = session.prd_content
        return JSONResponse(result)
    finally:
        db.close()


# ── Agent Handlers ───────────────────────────────────────────────────────────


async def api_list_agents(request: Request):
    status_filter = request.query_params.get("status")
    project_filter = request.query_params.get("project")
    db = _get_db()
    try:
        runs = agents_mod.list_agent_runs(db, status=status_filter, project_id=project_filter)
        return JSONResponse([_agent_run_dict(r) for r in runs])
    finally:
        db.close()


async def api_list_slots(request: Request):
    project_id = request.path_params["project_id"]
    status_filter = request.query_params.get("status")
    db = _get_db()
    try:
        slots = agents_mod.list_worktree_slots(db, project_id, status=status_filter)
        return JSONResponse([_slot_dict(s) for s in slots])
    finally:
        db.close()


def _session_dict(s) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "title": s.title,
        "phase": s.phase,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _agent_run_dict(r) -> dict:
    d = {
        "id": r.id,
        "task_id": r.task_id,
        "pid": r.pid,
        "status": r.status,
        "model": r.model,
        "backend": r.backend,
        "started_at": r.started_at.isoformat() if r.started_at else None,
    }
    if r.completed_at:
        d["completed_at"] = r.completed_at.isoformat()
    if r.exit_code is not None:
        d["exit_code"] = r.exit_code
    if r.result_summary:
        d["result_summary"] = r.result_summary
    return d


def _slot_dict(s) -> dict:
    d = {
        "id": s.id,
        "project_id": s.project_id,
        "path": s.path,
        "label": s.label,
        "status": s.status,
    }
    if s.branch:
        d["branch"] = s.branch
    if s.current_task_id:
        d["current_task_id"] = s.current_task_id
    return d


# ── WebSocket ────────────────────────────────────────────────────────────


async def ws_events(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming to the dashboard."""
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue()

    def on_event(event_type: str, payload: dict):
        try:
            queue.put_nowait(events_mod.to_json(event_type, payload))
        except asyncio.QueueFull:
            pass

    unsub = events_mod.subscribe(on_event)
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except Exception:
        pass
    finally:
        unsub()


# ── SPA catch-all ────────────────────────────────────────────────────────────


async def spa_catchall(request: Request):
    """Serve index.html for client-side routing (any non-API, non-static path)."""
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse(
        {"error": "Frontend not built. Run: cd frontend && npm run build"},
        status_code=404,
    )


# ── App ───────────────────────────────────────────────────────────────────────


def create_app() -> Starlette:
    routes = [
        # API routes
        Route("/api/projects", api_list_projects),
        Route("/api/projects/{project_id}", api_get_project),
        Route("/api/projects/{project_id}/tasks", api_project_tasks),
        Route("/api/projects/{project_id}/summary", api_project_summary),
        Route("/api/tasks/{task_id}", api_get_task),
        Route("/api/tasks/{task_id}/dispatch", api_dispatch_task, methods=["POST"]),
        Route("/api/worktrees", api_list_worktrees),
        # Planning (session CRUD — used by MCP tools)
        Route("/api/plan/start", api_plan_start, methods=["POST"]),
        Route("/api/plan/{session_id}/update", api_plan_update, methods=["PATCH", "POST"]),
        Route("/api/plan/sessions", api_plan_sessions),
        Route("/api/plan/{session_id}", api_plan_detail),
        # Agents
        Route("/api/agents", api_list_agents),
        Route("/api/projects/{project_id}/slots", api_list_slots),
        # WebSocket for real-time events
        WebSocketRoute("/ws", ws_events),
    ]

    # Serve built frontend static files if available
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
        routes.append(
            Mount("/assets", app=StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets"),
        )

    # SPA catch-all must be last
    routes.append(Route("/{path:path}", spa_catchall))

    return Starlette(routes=routes)


def run_server(host: str = "127.0.0.1", port: int = 8787):
    app = create_app()
    uvicorn.run(app, host=host, port=port)
