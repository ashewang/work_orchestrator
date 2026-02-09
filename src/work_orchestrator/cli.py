"""CLI entry point for the work orchestrator."""

import json
import sys

import click

from work_orchestrator.config import get_config
from work_orchestrator.core import memory as memory_mod
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import worktrees as worktrees_mod
from work_orchestrator.db.engine import get_db
from work_orchestrator.integrations import slack as slack_mod


def _get_db():
    config = get_config()
    return get_db(config.db_path)


@click.group()
def main():
    """wo - Work Orchestrator CLI"""
    pass


# ── Project Commands ──────────────────────────────────────────────────────────


@main.command("init")
@click.argument("project_name")
@click.option("--repo-path", default=".", help="Path to the git repository")
@click.option("--branch", default="main", help="Default branch name")
@click.option("--slack-channel", default=None, help="Default Slack channel")
def init_project(project_name, repo_path, branch, slack_channel):
    """Initialize a new project."""
    import os

    repo_path = os.path.abspath(repo_path)
    project_id = tasks_mod.slugify(project_name)

    with _get_db() as db:
        project = projects_mod.create_project(
            db, project_id, project_name, repo_path, branch, slack_channel
        )
        click.echo(f"Project created: {project.id} ({project.name})")
        click.echo(f"  Repo: {project.repo_path}")
        click.echo(f"  Branch: {project.default_branch}")


# ── Task Commands ─────────────────────────────────────────────────────────────


@main.group("task")
def task_group():
    """Manage tasks."""
    pass


@task_group.command("add")
@click.argument("title")
@click.option("--project", default="default", help="Project ID")
@click.option("--description", "-d", default="", help="Task description")
@click.option("--depends-on", default=None, help="Comma-separated task IDs this depends on")
def task_add(title, project, description, depends_on):
    """Create a new task."""
    deps = [d.strip() for d in depends_on.split(",")] if depends_on else None

    config = get_config()
    with _get_db() as db:
        projects_mod.ensure_default_project(db, str(config.repo_path))
        task = tasks_mod.create_task(db, title, project, description, depends_on=deps)
        click.echo(f"Created task: {task.id}")
        click.echo(f"  Title: {task.title}")
        click.echo(f"  Status: {task.status}")
        if task.depends_on:
            click.echo(f"  Depends on: {', '.join(task.depends_on)}")


@task_group.command("list")
@click.option("--project", default="default", help="Project ID")
@click.option("--status", default=None, help="Filter by status")
@click.option("--json-output", "--json", is_flag=True, help="Output as JSON")
def task_list(project, status, json_output):
    """List tasks."""
    with _get_db() as db:
        tasks = tasks_mod.list_tasks(db, project, status=status)

        if json_output:
            click.echo(json.dumps([_task_dict(t) for t in tasks], indent=2))
            return

        if not tasks:
            click.echo("No tasks found.")
            return

        status_icons = {
            "todo": "○",
            "in-progress": "●",
            "done": "✓",
            "blocked": "✗",
        }

        for task in tasks:
            icon = status_icons.get(task.status, "?")
            deps = f" [depends: {', '.join(task.depends_on)}]" if task.depends_on else ""
            wt = f" [worktree: {task.worktree_path}]" if task.worktree_path else ""
            click.echo(f"  {icon} {task.id}: {task.title} ({task.status}){deps}{wt}")

            # Show subtasks
            subtasks = tasks_mod.list_tasks(db, project, parent_task_id=task.id)
            for sub in subtasks:
                sub_icon = status_icons.get(sub.status, "?")
                click.echo(f"    {sub_icon} {sub.id}: {sub.title} ({sub.status})")


@task_group.command("show")
@click.argument("task_id")
def task_show(task_id):
    """Show task details."""
    with _get_db() as db:
        task = tasks_mod.get_task(db, task_id)
        if not task:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        click.echo(f"Task: {task.id}")
        click.echo(f"  Title: {task.title}")
        click.echo(f"  Status: {task.status}")
        click.echo(f"  Project: {task.project_id}")
        if task.description:
            click.echo(f"  Description: {task.description}")
        if task.branch_name:
            click.echo(f"  Branch: {task.branch_name}")
        if task.worktree_path:
            click.echo(f"  Worktree: {task.worktree_path}")
        if task.pr_url:
            click.echo(f"  PR: {task.pr_url}")
        if task.depends_on:
            click.echo(f"  Depends on: {', '.join(task.depends_on)}")
        if task.subtasks:
            click.echo(f"  Subtasks:")
            for sub in task.subtasks:
                click.echo(f"    - {sub.id}: {sub.title} ({sub.status})")
        if task.created_at:
            click.echo(f"  Created: {task.created_at}")

        events = tasks_mod.get_task_events(db, task_id)
        if events:
            click.echo(f"  History:")
            for e in events:
                click.echo(f"    [{e.created_at}] {e.event_type}: {e.old_value} -> {e.new_value}")


@task_group.command("start")
@click.argument("task_id")
@click.option("--branch", default=None, help="Custom branch name")
def task_start(task_id, branch):
    """Start a task - sets status to in-progress and creates a worktree."""
    config = get_config()
    with _get_db() as db:
        task = tasks_mod.get_task(db, task_id)
        if not task:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        tasks_mod.update_task_status(db, task_id, "in-progress")

        project = projects_mod.get_project(db, task.project_id)
        repo = project.repo_path if project else str(config.repo_path)

        try:
            wt = worktrees_mod.create_worktree_for_task(
                db, task_id, repo, config.worktree_dir, branch_name=branch
            )
            click.echo(f"Started task: {task_id}")
            click.echo(f"  Branch: {wt['branch']}")
            click.echo(f"  Worktree: {wt['worktree_path']}")
        except Exception as e:
            click.echo(f"Task started but worktree creation failed: {e}", err=True)


@task_group.command("done")
@click.argument("task_id")
@click.option("--keep-worktree", is_flag=True, help="Don't remove the worktree")
@click.option("--notify", default=None, help="Slack channel to notify")
def task_done(task_id, keep_worktree, notify):
    """Mark a task as done and clean up."""
    config = get_config()
    with _get_db() as db:
        task = tasks_mod.get_task(db, task_id)
        if not task:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        tasks_mod.update_task_status(db, task_id, "done")
        click.echo(f"Completed task: {task_id}")

        if not keep_worktree and task.worktree_path:
            project = projects_mod.get_project(db, task.project_id)
            repo = project.repo_path if project else str(config.repo_path)
            try:
                worktrees_mod.remove_worktree_for_task(db, task_id, repo)
                click.echo(f"  Worktree removed")
            except Exception as e:
                click.echo(f"  Worktree removal failed: {e}", err=True)

        if notify:
            try:
                blocks = slack_mod.format_task_notification(
                    task.id, task.title, "done", task.project_id
                )
                slack_mod.send_message(
                    config.slack_bot_token,
                    notify,
                    f"Task completed: {task.title}",
                    blocks,
                )
                click.echo(f"  Slack notification sent to {notify}")
            except Exception as e:
                click.echo(f"  Slack notification failed: {e}", err=True)


# ── Worktree Commands ────────────────────────────────────────────────────────


@main.group("worktree")
def worktree_group():
    """Manage git worktrees."""
    pass


@worktree_group.command("list")
def worktree_list():
    """List all worktrees and their linked tasks."""
    config = get_config()
    with _get_db() as db:
        wts = worktrees_mod.list_task_worktrees(db, str(config.repo_path))
        if not wts:
            click.echo("No worktrees found.")
            return
        for wt in wts:
            task_info = ""
            if "task_id" in wt:
                task_info = f" -> {wt['task_id']}: {wt.get('task_title', '')} ({wt.get('task_status', '')})"
            click.echo(f"  {wt['branch']} at {wt['path']}{task_info}")


@worktree_group.command("clean")
@click.option("--project", default="default", help="Project ID")
def worktree_clean(project):
    """Remove worktrees for all completed tasks."""
    config = get_config()
    with _get_db() as db:
        results = worktrees_mod.cleanup_done_worktrees(db, str(config.repo_path), project)
        if not results:
            click.echo("No worktrees to clean up.")
            return
        for r in results:
            if r.get("removed"):
                click.echo(f"  Removed: {r.get('path', r['task_id'])}")
            else:
                click.echo(f"  Skipped {r['task_id']}: {r.get('reason', 'unknown')}")


# ── Memory Commands ───────────────────────────────────────────────────────────


@main.group("memory")
def memory_group():
    """Manage persistent memory."""
    pass


@memory_group.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--category", default="general", help="Memory category")
def memory_set(key, value, category):
    """Store a memory entry."""
    with _get_db() as db:
        mem = memory_mod.remember(db, key, value, category)
        click.echo(f"Stored: {mem.key} = {mem.value} [{mem.category}]")


@memory_group.command("get")
@click.argument("key")
def memory_get(key):
    """Retrieve a memory by key."""
    with _get_db() as db:
        mem = memory_mod.recall_by_key(db, key)
        if not mem:
            click.echo(f"Not found: {key}", err=True)
            sys.exit(1)
        click.echo(f"{mem.key} = {mem.value} [{mem.category}]")


@memory_group.command("search")
@click.argument("query")
@click.option("--category", default=None, help="Filter by category")
def memory_search(query, category):
    """Full-text search across memories."""
    with _get_db() as db:
        mems = memory_mod.search_memories(db, query, category=category)
        if not mems:
            click.echo("No results.")
            return
        for m in mems:
            click.echo(f"  {m.key} = {m.value} [{m.category}]")


@memory_group.command("list")
@click.option("--category", default=None, help="Filter by category")
def memory_list(category):
    """List all memories."""
    with _get_db() as db:
        mems = memory_mod.list_memories(db, category=category)
        if not mems:
            click.echo("No memories stored.")
            return
        for m in mems:
            click.echo(f"  {m.key} = {m.value} [{m.category}]")


# ── Slack Commands ────────────────────────────────────────────────────────────


@main.group("slack")
def slack_group():
    """Slack integration commands."""
    pass


@slack_group.command("send")
@click.argument("channel")
@click.argument("message")
def slack_send(channel, message):
    """Send a message to a Slack channel."""
    config = get_config()
    try:
        result = slack_mod.send_message(config.slack_bot_token, channel, message)
        click.echo(f"Message sent to {result.channel} (ts: {result.ts})")
    except slack_mod.SlackError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@slack_group.command("status")
@click.option("--project", default="default", help="Project ID")
@click.option("--channel", default=None, help="Slack channel (uses project default if not set)")
def slack_status(project, channel):
    """Post a project status update to Slack."""
    config = get_config()
    with _get_db() as db:
        if not channel:
            proj = projects_mod.get_project(db, project)
            channel = proj.slack_channel if proj else None
        if not channel:
            click.echo("No channel specified and no default channel for project.", err=True)
            sys.exit(1)

        tasks = tasks_mod.list_tasks(db, project)
        task_dicts = [{"status": t.status} for t in tasks]
        blocks = slack_mod.format_status_update(project, task_dicts)
        try:
            result = slack_mod.send_message(
                config.slack_bot_token, channel, f"Status: {project}", blocks
            )
            click.echo(f"Status posted to {result.channel}")
        except slack_mod.SlackError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


# ── Dashboard Command ────────────────────────────────────────────────────────


@main.command("ui")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8787, type=int, help="Port to listen on")
@click.option("--open/--no-open", default=True, help="Open browser automatically")
def ui_command(host, port, open):
    """Launch the web dashboard."""
    import webbrowser

    from work_orchestrator.web.app import run_server

    url = f"http://{host}:{port}"
    click.echo(f"Starting dashboard at {url}")
    if open:
        webbrowser.open(url)
    run_server(host=host, port=port)


# ── MCP Server Command ───────────────────────────────────────────────────────


@main.group("mcp")
def mcp_group():
    """MCP server commands."""
    pass


@mcp_group.command("serve")
def mcp_serve():
    """Start the MCP server (stdio transport)."""
    from work_orchestrator.mcp.server import mcp
    from work_orchestrator.mcp import prompts  # noqa: F401 - registers prompts

    mcp.run(transport="stdio")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _task_dict(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "project": task.project_id,
        "description": task.description,
        "branch": task.branch_name,
        "worktree": task.worktree_path,
        "pr_url": task.pr_url,
        "depends_on": task.depends_on,
    }


if __name__ == "__main__":
    main()
