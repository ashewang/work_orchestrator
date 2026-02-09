"""Task management operations."""

import re
import sqlite3
from datetime import datetime

from work_orchestrator.db.models import Task, TaskEvent


def slugify(title: str) -> str:
    """Convert a title to a URL-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:60]


def _unique_id(db: sqlite3.Connection, base_slug: str) -> str:
    """Generate a unique task ID from a slug, appending a number if needed."""
    existing = db.execute(
        "SELECT id FROM tasks WHERE id = ?", (base_slug,)
    ).fetchone()
    if not existing:
        return base_slug

    i = 2
    while True:
        candidate = f"{base_slug}-{i}"
        existing = db.execute(
            "SELECT id FROM tasks WHERE id = ?", (candidate,)
        ).fetchone()
        if not existing:
            return candidate
        i += 1


def create_task(
    db: sqlite3.Connection,
    title: str,
    project_id: str = "default",
    description: str = "",
    parent_task_id: str | None = None,
    depends_on: list[str] | None = None,
    pr_url: str | None = None,
    priority: int = 3,
) -> Task:
    """Create a new task."""
    task_id = _unique_id(db, slugify(title))
    priority = max(0, min(6, priority))

    db.execute(
        """INSERT INTO tasks (id, project_id, title, description, parent_task_id, pr_url, priority)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, project_id, title, description, parent_task_id, pr_url, priority),
    )

    if depends_on:
        for dep_id in depends_on:
            db.execute(
                "INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)",
                (task_id, dep_id),
            )

    _log_event(db, task_id, "created", None, "todo")
    db.commit()
    return get_task(db, task_id)


def get_task(db: sqlite3.Connection, task_id: str) -> Task | None:
    """Get a task by ID with its dependencies."""
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None

    task = _row_to_task(row)

    deps = db.execute(
        "SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?",
        (task_id,),
    ).fetchall()
    task.depends_on = [d["depends_on_task_id"] for d in deps]

    subtasks = db.execute(
        "SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY priority ASC, created_at ASC",
        (task_id,),
    ).fetchall()
    task.subtasks = [_row_to_task(s) for s in subtasks]

    return task


def list_tasks(
    db: sqlite3.Connection,
    project_id: str = "default",
    status: str | None = None,
    parent_task_id: str | None = None,
) -> list[Task]:
    """List tasks with optional filters."""
    query = "SELECT * FROM tasks WHERE project_id = ?"
    params: list = [project_id]

    if status:
        query += " AND status = ?"
        params.append(status)

    if parent_task_id is not None:
        query += " AND parent_task_id = ?"
        params.append(parent_task_id)
    else:
        query += " AND parent_task_id IS NULL"

    query += " ORDER BY priority ASC, created_at ASC"
    rows = db.execute(query, params).fetchall()
    tasks = []
    for row in rows:
        task = _row_to_task(row)
        deps = db.execute(
            "SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?",
            (task.id,),
        ).fetchall()
        task.depends_on = [d["depends_on_task_id"] for d in deps]
        tasks.append(task)
    return tasks


def update_task_status(
    db: sqlite3.Connection,
    task_id: str,
    status: str,
) -> Task | None:
    """Update a task's status. Returns the updated task."""
    task = get_task(db, task_id)
    if not task:
        return None

    old_status = task.status
    updates = {"status": status}

    if status == "done" and old_status != "done":
        updates["completed_at"] = datetime.now().isoformat()

    set_parts = [f"{k} = ?" for k in updates]
    set_parts.append("updated_at = datetime('now')")
    values = list(updates.values()) + [task_id]

    db.execute(
        f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ?",
        values,
    )
    _log_event(db, task_id, "status_changed", old_status, status)
    db.commit()
    return get_task(db, task_id)


def break_down_task(
    db: sqlite3.Connection,
    task_id: str,
    subtasks: list[dict],
) -> list[Task]:
    """Break a task into subtasks. Each dict should have 'title' and optionally 'description' and 'depends_on'."""
    created = []
    for sub in subtasks:
        t = create_task(
            db,
            title=sub["title"],
            project_id=get_task(db, task_id).project_id,
            description=sub.get("description", ""),
            parent_task_id=task_id,
            depends_on=sub.get("depends_on"),
            priority=sub.get("priority", 3),
        )
        created.append(t)
    return created


def delete_task(db: sqlite3.Connection, task_id: str) -> bool:
    """Delete a task and its subtasks."""
    task = get_task(db, task_id)
    if not task:
        return False

    # Delete subtasks first
    for subtask in task.subtasks:
        delete_task(db, subtask.id)

    db.execute("DELETE FROM task_dependencies WHERE task_id = ? OR depends_on_task_id = ?", (task_id, task_id))
    db.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return True


def get_task_events(db: sqlite3.Connection, task_id: str) -> list[TaskEvent]:
    """Get the event history for a task."""
    rows = db.execute(
        "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at",
        (task_id,),
    ).fetchall()
    return [
        TaskEvent(
            id=r["id"],
            task_id=r["task_id"],
            event_type=r["event_type"],
            old_value=r["old_value"],
            new_value=r["new_value"],
            created_at=_parse_dt(r["created_at"]),
        )
        for r in rows
    ]


def get_blocked_tasks(db: sqlite3.Connection, project_id: str = "default") -> list[Task]:
    """Get tasks whose dependencies are not all 'done'."""
    tasks = list_tasks(db, project_id, status="todo")
    blocked = []
    for task in tasks:
        if task.depends_on:
            for dep_id in task.depends_on:
                dep = get_task(db, dep_id)
                if dep and dep.status != "done":
                    blocked.append(task)
                    break
    return blocked


def get_ready_tasks(db: sqlite3.Connection, project_id: str = "default") -> list[Task]:
    """Get tasks that are 'todo' and have all dependencies met."""
    tasks = list_tasks(db, project_id, status="todo")
    ready = []
    for task in tasks:
        if not task.depends_on:
            ready.append(task)
            continue
        all_done = all(
            (dep := get_task(db, dep_id)) and dep.status == "done"
            for dep_id in task.depends_on
        )
        if all_done:
            ready.append(task)
    return ready


def _log_event(
    db: sqlite3.Connection,
    task_id: str,
    event_type: str,
    old_value: str | None,
    new_value: str | None,
):
    db.execute(
        "INSERT INTO task_events (task_id, event_type, old_value, new_value) VALUES (?, ?, ?, ?)",
        (task_id, event_type, old_value, new_value),
    )


def update_task_pr_url(
    db: sqlite3.Connection,
    task_id: str,
    pr_url: str | None,
) -> Task | None:
    """Set or clear a task's PR URL."""
    task = get_task(db, task_id)
    if not task:
        return None
    old_url = task.pr_url
    db.execute(
        "UPDATE tasks SET pr_url = ?, updated_at = datetime('now') WHERE id = ?",
        (pr_url, task_id),
    )
    _log_event(db, task_id, "pr_url_changed", old_url, pr_url)
    db.commit()
    return get_task(db, task_id)


def update_task_priority(
    db: sqlite3.Connection,
    task_id: str,
    priority: int,
) -> Task | None:
    """Update a task's priority (P0-P6, 0=highest)."""
    task = get_task(db, task_id)
    if not task:
        return None
    priority = max(0, min(6, priority))
    old_priority = task.priority
    db.execute(
        "UPDATE tasks SET priority = ?, updated_at = datetime('now') WHERE id = ?",
        (priority, task_id),
    )
    _log_event(db, task_id, "priority_changed", str(old_priority), str(priority))
    db.commit()
    return get_task(db, task_id)


def add_dependency(
    db: sqlite3.Connection,
    task_id: str,
    depends_on_id: str,
) -> Task | None:
    """Add a dependency to an existing task."""
    task = get_task(db, task_id)
    if not task:
        return None
    dep = get_task(db, depends_on_id)
    if not dep:
        raise ValueError(f"Dependency task not found: {depends_on_id}")
    if depends_on_id in task.depends_on:
        return task  # Already exists
    db.execute(
        "INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)",
        (task_id, depends_on_id),
    )
    _log_event(db, task_id, "dependency_added", None, depends_on_id)
    db.commit()
    return get_task(db, task_id)


def remove_dependency(
    db: sqlite3.Connection,
    task_id: str,
    depends_on_id: str,
) -> Task | None:
    """Remove a dependency from a task."""
    task = get_task(db, task_id)
    if not task:
        return None
    db.execute(
        "DELETE FROM task_dependencies WHERE task_id = ? AND depends_on_task_id = ?",
        (task_id, depends_on_id),
    )
    _log_event(db, task_id, "dependency_removed", depends_on_id, None)
    db.commit()
    return get_task(db, task_id)


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        description=row["description"],
        status=row["status"],
        priority=row["priority"] if row["priority"] is not None else 3,
        parent_task_id=row["parent_task_id"],
        branch_name=row["branch_name"],
        worktree_path=row["worktree_path"],
        pr_url=row["pr_url"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        completed_at=_parse_dt(row["completed_at"]),
    )


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)
