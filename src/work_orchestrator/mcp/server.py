"""MCP server exposing all work orchestrator tools."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP

from work_orchestrator.config import get_config
from work_orchestrator.core import agents as agents_mod
from work_orchestrator.core import memory as memory_mod
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import specs as specs_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import worktrees as worktrees_mod
from work_orchestrator.core.agents import AgentMonitor
from work_orchestrator.db.engine import init_db
from work_orchestrator.integrations import slack as slack_mod


@dataclass
class AppContext:
    db: sqlite3.Connection
    config: object
    agent_monitor: AgentMonitor | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize DB connection on startup, close on shutdown."""
    config = get_config()
    db = init_db(config.db_path)

    monitor = AgentMonitor(
        db_path=config.db_path,
        slack_token=config.slack_bot_token,
    )
    monitor.start()

    try:
        yield AppContext(db=db, config=config, agent_monitor=monitor)
    finally:
        monitor.stop()
        db.close()


mcp = FastMCP("work-orchestrator", lifespan=app_lifespan)


def _ctx(ctx: Context) -> AppContext:
    """Extract AppContext from MCP Context."""
    return ctx.request_context.lifespan_context


def _cfg(ctx: Context):
    return _ctx(ctx).config


# ── Task Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
def create_task(
    ctx: Context,
    title: str,
    project: str = "default",
    description: str = "",
    depends_on: list[str] | None = None,
    priority: int = 3,
) -> dict:
    """Create a new task. Priority: P0 (highest) to P6 (lowest), default P3."""
    app = _ctx(ctx)
    projects_mod.ensure_default_project(app.db, str(_cfg(ctx).repo_path))
    task = tasks_mod.create_task(
        app.db, title, project, description, depends_on=depends_on, priority=priority
    )
    return _task_to_dict(task)


@mcp.tool()
def list_tasks(
    ctx: Context,
    project: str = "default",
    status: str | None = None,
) -> list[dict]:
    """List all tasks, optionally filtered by project and status."""
    app = _ctx(ctx)
    tasks = tasks_mod.list_tasks(app.db, project, status=status)
    return [_task_to_dict(t) for t in tasks]


@mcp.tool()
def get_task(ctx: Context, task_id: str) -> dict:
    """Get full details of a task including dependencies and subtasks."""
    app = _ctx(ctx)
    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    return _task_to_dict(task)


@mcp.tool()
def update_task_status(ctx: Context, task_id: str, status: str) -> dict:
    """Update a task's status. Valid statuses: todo, in-progress, done, blocked, review.

    Use create_worktree / remove_worktree separately if you need a worktree.
    """
    app = _ctx(ctx)

    task = tasks_mod.update_task_status(app.db, task_id, status)
    if not task:
        return {"error": f"Task not found: {task_id}"}

    return _task_to_dict(task)


@mcp.tool()
def break_down_task(ctx: Context, task_id: str, subtasks: list[dict]) -> list[dict]:
    """Break a task into subtasks. Each subtask dict should have 'title' and optionally 'description' and 'depends_on'."""
    app = _ctx(ctx)
    created = tasks_mod.break_down_task(app.db, task_id, subtasks)
    return [_task_to_dict(t) for t in created]


@mcp.tool()
def delete_task(ctx: Context, task_id: str) -> dict:
    """Delete a task and its subtasks. Also removes any associated worktree."""
    app = _ctx(ctx)
    config = _cfg(ctx)

    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}

    if task.worktree_path:
        project = projects_mod.get_project(app.db, task.project_id)
        repo = project.repo_path if project else str(config.repo_path)
        worktrees_mod.remove_worktree_for_task(app.db, task_id, repo, force=True)

    tasks_mod.delete_task(app.db, task_id)
    return {"deleted": task_id}


@mcp.tool()
def get_ready_tasks(ctx: Context, project: str = "default") -> list[dict]:
    """Get tasks that are ready to start (all dependencies met)."""
    app = _ctx(ctx)
    tasks = tasks_mod.get_ready_tasks(app.db, project)
    return [_task_to_dict(t) for t in tasks]


@mcp.tool()
def update_task_pr_url(ctx: Context, task_id: str, pr_url: str) -> dict:
    """Set the PR URL for a task (e.g. after creating a pull request)."""
    app = _ctx(ctx)
    task = tasks_mod.update_task_pr_url(app.db, task_id, pr_url)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    return _task_to_dict(task)


@mcp.tool()
def update_task_priority(ctx: Context, task_id: str, priority: int) -> dict:
    """Update a task's priority. P0 (highest urgency) to P6 (lowest)."""
    app = _ctx(ctx)
    if not 0 <= priority <= 6:
        return {"error": "Priority must be between 0 (P0) and 6 (P6)"}
    task = tasks_mod.update_task_priority(app.db, task_id, priority)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    return _task_to_dict(task)


@mcp.tool()
def add_dependency(ctx: Context, task_id: str, depends_on_id: str) -> dict:
    """Add a dependency to a task. The task will be blocked until the dependency is done."""
    app = _ctx(ctx)
    try:
        task = tasks_mod.add_dependency(app.db, task_id, depends_on_id)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        return _task_to_dict(task)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def remove_dependency(ctx: Context, task_id: str, depends_on_id: str) -> dict:
    """Remove a dependency from a task."""
    app = _ctx(ctx)
    task = tasks_mod.remove_dependency(app.db, task_id, depends_on_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    return _task_to_dict(task)


# ── Worktree Tools ────────────────────────────────────────────────────────────


@mcp.tool()
def create_worktree(
    ctx: Context,
    task_id: str,
    branch_name: str | None = None,
    base_branch: str = "main",
) -> dict:
    """Create a git worktree for a task. Returns the worktree path and branch."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    project = projects_mod.get_project(app.db, task.project_id)
    repo = project.repo_path if project else str(config.repo_path)
    return worktrees_mod.create_worktree_for_task(
        app.db, task_id, repo, config.worktree_dir, base_branch, branch_name
    )


@mcp.tool()
def list_worktrees(ctx: Context) -> list[dict]:
    """List all git worktrees and their linked tasks."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    return worktrees_mod.list_task_worktrees(app.db, str(config.repo_path))


@mcp.tool()
def remove_worktree(ctx: Context, task_id: str, force: bool = False) -> dict:
    """Remove the git worktree for a task."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}
    project = projects_mod.get_project(app.db, task.project_id)
    repo = project.repo_path if project else str(config.repo_path)
    return worktrees_mod.remove_worktree_for_task(app.db, task_id, repo, force=force)


@mcp.tool()
def worktree_status(ctx: Context, task_id: str) -> dict:
    """Get git status for a task's worktree."""
    app = _ctx(ctx)
    return worktrees_mod.get_worktree_status(app.db, task_id)


# ── Slack Tools ───────────────────────────────────────────────────────────────


@mcp.tool()
def send_slack_message(ctx: Context, channel: str, message: str) -> dict:
    """Send a message to a Slack channel."""
    config = _cfg(ctx)
    try:
        result = slack_mod.send_message(config.slack_bot_token, channel, message)
        return {"channel": result.channel, "ts": result.ts}
    except slack_mod.SlackError as e:
        return {"error": str(e)}


@mcp.tool()
def notify_task_complete(ctx: Context, task_id: str, channel: str) -> dict:
    """Send a formatted task completion notification to Slack."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}

    blocks = slack_mod.format_task_notification(
        task.id, task.title, task.status, task.project_id
    )
    try:
        result = slack_mod.send_message(
            config.slack_bot_token, channel, f"Task update: {task.title}", blocks
        )
        return {"channel": result.channel, "ts": result.ts}
    except slack_mod.SlackError as e:
        return {"error": str(e)}


@mcp.tool()
def draft_pr_review_request(
    ctx: Context, task_id: str, channel: str, pr_url: str | None = None
) -> dict:
    """Post a PR review request to Slack with task context."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    task = tasks_mod.get_task(app.db, task_id)
    if not task:
        return {"error": f"Task not found: {task_id}"}

    blocks = slack_mod.format_pr_review_request(
        task.id, task.title, task.branch_name or "unknown", pr_url
    )
    try:
        result = slack_mod.send_message(
            config.slack_bot_token,
            channel,
            f"Review requested: {task.title}",
            blocks,
        )
        return {"channel": result.channel, "ts": result.ts}
    except slack_mod.SlackError as e:
        return {"error": str(e)}


@mcp.tool()
def post_status_update(
    ctx: Context, project: str = "default", channel: str | None = None
) -> dict:
    """Post a project status summary to Slack."""
    app = _ctx(ctx)
    config = _cfg(ctx)

    if not channel:
        proj = projects_mod.get_project(app.db, project)
        channel = proj.slack_channel if proj else None
    if not channel:
        return {"error": "No channel specified and no default channel for project"}

    tasks = tasks_mod.list_tasks(app.db, project)
    task_dicts = [{"status": t.status} for t in tasks]
    blocks = slack_mod.format_status_update(project, task_dicts)
    try:
        result = slack_mod.send_message(
            config.slack_bot_token, channel, f"Status update: {project}", blocks
        )
        return {"channel": result.channel, "ts": result.ts}
    except slack_mod.SlackError as e:
        return {"error": str(e)}


# ── Memory Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def remember(
    ctx: Context,
    key: str,
    value: str,
    category: str = "general",
) -> dict:
    """Store a piece of context, decision, or note for later recall."""
    app = _ctx(ctx)
    mem = memory_mod.remember(app.db, key, value, category)
    return {"key": mem.key, "value": mem.value, "category": mem.category}


@mcp.tool()
def recall(
    ctx: Context,
    key: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """Retrieve stored context. Use 'key' for exact lookup, 'search' for full-text search, or 'category' to filter."""
    app = _ctx(ctx)

    if key:
        mem = memory_mod.recall_by_key(app.db, key)
        if mem:
            return [{"key": mem.key, "value": mem.value, "category": mem.category}]
        return []

    if search:
        mems = memory_mod.search_memories(app.db, search, category=category)
    else:
        mems = memory_mod.list_memories(app.db, category=category)

    return [{"key": m.key, "value": m.value, "category": m.category} for m in mems]


@mcp.tool()
def forget(ctx: Context, key: str) -> dict:
    """Remove a memory entry by key."""
    app = _ctx(ctx)
    deleted = memory_mod.forget(app.db, key)
    return {"deleted": deleted, "key": key}


@mcp.tool()
def list_memories(ctx: Context, category: str | None = None) -> list[dict]:
    """List all stored memories, optionally filtered by category."""
    app = _ctx(ctx)
    mems = memory_mod.list_memories(app.db, category=category)
    return [{"key": m.key, "value": m.value, "category": m.category} for m in mems]


@mcp.tool()
def setup_profile(
    ctx: Context,
    name: str,
    language: str | None = None,
    vibe: str | None = None,
) -> dict:
    """Set up your personal profile for the work orchestrator.

    This stores your preferences so greetings and interactions feel personalized.
    - name: Your name (e.g. "Ashe")
    - language: Your preferred communication language (e.g. "English", "中文", "日本語")
    - vibe: How you like interactions to feel (e.g. "chill", "hype", "professional")
    """
    app = _ctx(ctx)
    memory_mod.remember(app.db, "user_name", name, category="profile")
    if language:
        memory_mod.remember(app.db, "preferred_language", language, category="profile")
    if vibe:
        memory_mod.remember(app.db, "vibe", vibe, category="profile")
    return {
        "name": name,
        "language": language,
        "vibe": vibe,
        "message": f"Welcome, {name}! Profile saved.",
    }


@mcp.tool()
def get_profile(ctx: Context) -> dict:
    """Get the current user profile."""
    app = _ctx(ctx)
    mems = memory_mod.list_memories(app.db, category="profile")
    return {m.key: m.value for m in mems}


# ── Spec Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
def save_spec(
    ctx: Context,
    project_id: str,
    title: str,
    content: str,
    source_url: str | None = None,
) -> dict:
    """Save a spec (design doc, API spec, reference material) for a project.

    If a spec with the same title already exists for the project, it will be updated.
    """
    app = _ctx(ctx)
    spec = specs_mod.save_spec(app.db, project_id, title, content, source_url)
    return _spec_to_dict(spec)


@mcp.tool()
def get_spec(ctx: Context, spec_id: str) -> dict:
    """Retrieve a spec by ID, including its full content."""
    app = _ctx(ctx)
    spec = specs_mod.get_spec(app.db, spec_id)
    if not spec:
        return {"error": f"Spec '{spec_id}' not found"}
    return _spec_to_dict(spec)


@mcp.tool()
def list_specs(ctx: Context, project_id: str | None = None) -> list[dict]:
    """List specs, optionally filtered by project. Returns titles without full content."""
    app = _ctx(ctx)
    specs = specs_mod.list_specs(app.db, project_id)
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "title": s.title,
            "source_url": s.source_url,
            "updated_at": str(s.updated_at) if s.updated_at else None,
        }
        for s in specs
    ]


@mcp.tool()
def update_spec(
    ctx: Context,
    spec_id: str,
    title: str | None = None,
    content: str | None = None,
) -> dict:
    """Update a spec's title and/or content."""
    app = _ctx(ctx)
    spec = specs_mod.update_spec(app.db, spec_id, title, content)
    if not spec:
        return {"error": f"Spec '{spec_id}' not found"}
    return _spec_to_dict(spec)


@mcp.tool()
def delete_spec(ctx: Context, spec_id: str) -> dict:
    """Delete a spec by ID."""
    app = _ctx(ctx)
    deleted = specs_mod.delete_spec(app.db, spec_id)
    return {"deleted": deleted, "spec_id": spec_id}


@mcp.tool()
def fetch_and_save_spec(
    ctx: Context,
    url: str,
    project_id: str,
    title: str | None = None,
) -> dict:
    """Fetch content from a URL and save it as a spec.

    Useful for storing API docs, design docs, or reference material from the web.
    Title is auto-derived from URL if not provided.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed to fetch URL: {e}"}

    spec_title = title or url.rsplit("/", 1)[-1] or url
    app = _ctx(ctx)
    spec = specs_mod.save_spec(app.db, project_id, spec_title, content, source_url=url)
    return _spec_to_dict(spec)


def _spec_to_dict(spec) -> dict:
    return {
        "id": spec.id,
        "project_id": spec.project_id,
        "title": spec.title,
        "content": spec.content,
        "source_url": spec.source_url,
        "created_at": str(spec.created_at) if spec.created_at else None,
        "updated_at": str(spec.updated_at) if spec.updated_at else None,
    }


# ── Project Tools ─────────────────────────────────────────────────────────────


@mcp.tool()
def init_project(
    ctx: Context,
    project_id: str,
    name: str,
    repo_path: str | None = None,
    default_branch: str = "main",
    slack_channel: str | None = None,
) -> dict:
    """Initialize a new project."""
    app = _ctx(ctx)
    config = _cfg(ctx)
    path = repo_path or str(config.repo_path)
    project = projects_mod.create_project(
        app.db, project_id, name, path, default_branch, slack_channel
    )
    return {
        "id": project.id,
        "name": project.name,
        "repo_path": project.repo_path,
        "default_branch": project.default_branch,
        "slack_channel": project.slack_channel,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _task_to_dict(task) -> dict:
    d = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": f"P{task.priority}",
        "project": task.project_id,
        "description": task.description,
    }
    if task.parent_task_id:
        d["parent_task_id"] = task.parent_task_id
    if task.branch_name:
        d["branch"] = task.branch_name
    if task.worktree_path:
        d["worktree_path"] = task.worktree_path
    if task.pr_url:
        d["pr_url"] = task.pr_url
    if task.depends_on:
        d["depends_on"] = task.depends_on
    if task.subtasks:
        d["subtasks"] = [_task_to_dict(s) for s in task.subtasks]
    return d


def _slot_to_dict(slot) -> dict:
    d = {
        "id": slot.id,
        "project_id": slot.project_id,
        "path": slot.path,
        "label": slot.label,
        "status": slot.status,
    }
    if slot.branch:
        d["branch"] = slot.branch
    if slot.current_task_id:
        d["current_task_id"] = slot.current_task_id
    return d


def _agent_run_to_dict(run) -> dict:
    d = {
        "id": run.id,
        "task_id": run.task_id,
        "pid": run.pid,
        "status": run.status,
        "model": run.model,
        "backend": run.backend,
        "started_at": run.started_at.isoformat() if run.started_at else None,
    }
    if run.max_budget:
        d["max_budget"] = run.max_budget
    if run.completed_at:
        d["completed_at"] = run.completed_at.isoformat()
    if run.exit_code is not None:
        d["exit_code"] = run.exit_code
    if run.result_summary:
        d["result_summary"] = run.result_summary
    if run.output_file:
        d["output_file"] = run.output_file
    return d


# ── Agent Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def register_worktrees(ctx: Context, project: str) -> list[dict]:
    """Auto-discover and register git worktrees as available slots for a project.
    Finds all worktrees in the project's repo and registers any not already tracked."""
    app = _ctx(ctx)
    project_obj = projects_mod.get_project(app.db, project)
    if not project_obj:
        return [{"error": f"Project not found: {project}"}]
    slots = agents_mod.discover_and_register_worktrees(
        app.db, project, project_obj.repo_path
    )
    return [_slot_to_dict(s) for s in slots]


@mcp.tool()
def list_slots(ctx: Context, project: str, status: str | None = None) -> list[dict]:
    """List worktree slots for a project. Filter by status: 'available' or 'occupied'."""
    app = _ctx(ctx)
    slots = agents_mod.list_worktree_slots(app.db, project, status=status)
    return [_slot_to_dict(s) for s in slots]


@mcp.tool()
def assign_task(ctx: Context, task_id: str, slot_label: str, project: str = "default") -> dict:
    """Assign a task to an available worktree slot by label (e.g. 'glockenspiel_ashe1')."""
    app = _ctx(ctx)
    slot = agents_mod.get_slot_by_label(app.db, project, slot_label)
    if not slot:
        return {"error": f"Slot not found: '{slot_label}' in project '{project}'"}
    try:
        updated = agents_mod.assign_task_to_slot(app.db, task_id, slot.id)
        return _slot_to_dict(updated)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def launch_agent(
    ctx: Context,
    task_id: str,
    instructions: str,
    model: str | None = None,
    max_budget: float | None = None,
    backend: str | None = None,
) -> dict:
    """Launch an agent sub-process to work on a task autonomously.
    The task must be assigned to a worktree slot first.
    The agent runs in the background; use agent_status to check progress.
    Prefer using delegate_task instead — it handles slot assignment automatically.

    Args:
        backend: Agent backend to use (claude-code, opencode, pi). Default: project/config default.
    """
    app = _ctx(ctx)
    config = _cfg(ctx)
    m = model or config.agent_default_model
    b = max_budget or config.agent_default_budget
    try:
        run = agents_mod.launch_agent(
            app.db, task_id, instructions,
            output_dir=config.agent_output_dir,
            model=m,
            max_budget=b,
            backend=backend or config.default_backend,
        )
        return _agent_run_to_dict(run)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def delegate_task(
    ctx: Context,
    task_id: str,
    instructions: str,
    model: str | None = None,
    max_budget: float | None = None,
    max_turns: int | None = None,
    slot_label: str | None = None,
    project: str | None = None,
    terminal: bool = True,
    backend: str | None = None,
) -> dict:
    """Delegate a task to a sub-agent in one step.

    Automatically picks an available worktree slot (or use slot_label to pick one),
    assigns the task, and launches an agent with MCP access to work-orchestrator tools.

    By default, opens the agent in a new Terminal window so you can watch it work.
    Use agent_status to check progress, or wait for completion notification.

    Args:
        task_id: The task to delegate
        instructions: What the agent should do (be specific and detailed)
        model: Model to use (default: config default, usually "sonnet")
        max_budget: Max spend in USD (default: config default)
        max_turns: Max tool-use turns (default: 25). Higher for complex tasks.
        slot_label: Specific worktree slot label (auto-picks if omitted)
        project: Project ID (auto-detected from task if omitted)
        terminal: Open in a Terminal window (default: true). Set false for background.
        backend: Agent backend to use (claude-code, opencode, pi). Resolves from task → project → config default.
    """
    app = _ctx(ctx)
    config = _cfg(ctx)
    m = model or config.agent_default_model
    b = max_budget or config.agent_default_budget
    t = max_turns or config.agent_default_max_turns
    try:
        run = agents_mod.delegate_task(
            app.db,
            task_id=task_id,
            instructions=instructions,
            output_dir=config.agent_output_dir,
            project_id=project,
            model=m,
            max_budget=b,
            max_turns=t,
            slot_label=slot_label,
            terminal=terminal,
            backend=backend or config.default_backend,
        )
        return _agent_run_to_dict(run)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def release_slot(ctx: Context, slot_label: str, project: str = "default") -> dict:
    """Release a worktree slot, making it available for new tasks.

    Use this after an agent finishes or a task no longer needs the slot.
    """
    app = _ctx(ctx)
    slot = agents_mod.get_slot_by_label(app.db, project, slot_label)
    if not slot:
        return {"error": f"Slot not found: '{slot_label}' in project '{project}'"}
    try:
        updated = agents_mod.release_slot(app.db, slot.id)
        return _slot_to_dict(updated)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def agent_status(ctx: Context, task_id: str) -> dict:
    """Check the status of the latest agent run for a task."""
    app = _ctx(ctx)
    run = agents_mod.get_latest_agent_run(app.db, task_id)
    if not run:
        return {"error": f"No agent runs found for task: {task_id}"}
    return _agent_run_to_dict(run)


@mcp.tool()
def list_agents(ctx: Context, status: str | None = None, project: str | None = None) -> list[dict]:
    """List all agent runs, optionally filtered by status (running/completed/failed/cancelled)."""
    app = _ctx(ctx)
    runs = agents_mod.list_agent_runs(app.db, status=status, project_id=project)
    return [_agent_run_to_dict(r) for r in runs]


@mcp.tool()
def cancel_agent(ctx: Context, task_id: str) -> dict:
    """Cancel a running agent for a task."""
    app = _ctx(ctx)
    run = agents_mod.cancel_agent(app.db, task_id)
    if not run:
        return {"error": f"No running agent found for task: {task_id}"}
    return _agent_run_to_dict(run)


@mcp.tool()
def get_agent_output(ctx: Context, task_id: str) -> dict:
    """Read the captured output of the latest agent run for a task."""
    app = _ctx(ctx)
    output = agents_mod.get_agent_output(app.db, task_id)
    if output is None:
        return {"error": f"No output found for task: {task_id}"}
    if len(output) > 10000:
        return {"output": output[:10000], "truncated": True, "total_length": len(output)}
    return {"output": output, "truncated": False}


# ── Planning Tools ───────────────────────────────────────────────────────────


@mcp.tool()
def start_planning(ctx: Context, project_id: str, title: str = "") -> dict:
    """Start a new CCPM-style planning session for a project.

    Returns a session ID. Use plan_message to have a multi-turn brainstorm conversation,
    then approve_prd to generate a PRD, and approve_plan to create tasks.
    """
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    project = projects_mod.get_project(app.db, project_id)
    if not project:
        return {"error": f"Project not found: {project_id}"}
    session = planner.create_session(app.db, title or f"Planning for {project_id}", project_id=project_id)
    return _session_to_dict(session)


@mcp.tool()
def plan_message(ctx: Context, session_id: str, message: str) -> dict:
    """Send a message in a planning session and get Claude's response.

    Use this for brainstorming: discuss scope, ask questions, refine ideas.
    The full conversation is preserved for PRD generation later.
    """
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    try:
        response = planner.plan_message(app.db, session_id, message)
        return {"response": response}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Planning API error: {e}"}


@mcp.tool()
def approve_prd(ctx: Context, session_id: str) -> dict:
    """Generate a PRD from the brainstorm conversation and advance to the PRD phase.

    Call this after enough brainstorming. Returns the PRD markdown.
    """
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    try:
        prd = planner.generate_prd(app.db, session_id)
        session = planner.get_session(app.db, session_id)
        return {"prd": prd, "session": _session_to_dict(session)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"PRD generation error: {e}"}


@mcp.tool()
def decompose_plan(ctx: Context, session_id: str) -> dict:
    """Decompose the PRD into concrete tasks (without creating them yet).

    Returns a list of proposed tasks. Call approve_plan to actually create them.
    """
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    try:
        tasks = planner.decompose_prd(app.db, session_id)
        return {"tasks": tasks, "count": len(tasks)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Decomposition error: {e}"}


@mcp.tool()
def approve_plan(ctx: Context, session_id: str, tasks: list[dict]) -> dict:
    """Create tasks in the DB from a decomposed plan. Finalizes the planning session.

    Pass the tasks array from decompose_plan. Returns the created task objects.
    """
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    try:
        created = planner.approve_plan(app.db, session_id, tasks)
        return {
            "created": [_task_to_dict(t) for t in created],
            "count": len(created),
        }
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def list_planning_sessions(ctx: Context, project_id: str | None = None) -> list[dict]:
    """List planning sessions, optionally filtered by project."""
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    sessions = planner.list_sessions(app.db, project_id=project_id)
    return [_session_to_dict(s) for s in sessions]


@mcp.tool()
def get_planning_session(ctx: Context, session_id: str) -> dict:
    """Get full details of a planning session including conversation and PRD."""
    from work_orchestrator.core import planner

    app = _ctx(ctx)
    session = planner.get_session(app.db, session_id)
    if not session:
        return {"error": f"Session not found: {session_id}"}
    messages = planner.get_messages(app.db, session_id)
    result = _session_to_dict(session)
    result["messages"] = [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in messages
    ]
    return result


def _session_to_dict(session) -> dict:
    d = {
        "id": session.id,
        "project_id": session.project_id,
        "title": session.title,
        "phase": session.phase,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
    if session.prd_content:
        d["has_prd"] = True
    return d
