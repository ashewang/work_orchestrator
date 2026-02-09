"""Project management operations."""

import sqlite3
from datetime import datetime

from work_orchestrator.db.models import Project


def create_project(
    db: sqlite3.Connection,
    project_id: str,
    name: str,
    repo_path: str,
    default_branch: str = "main",
    slack_channel: str | None = None,
) -> Project:
    """Create a new project."""
    db.execute(
        """INSERT INTO projects (id, name, repo_path, default_branch, slack_channel)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, name, repo_path, default_branch, slack_channel),
    )
    db.commit()
    return get_project(db, project_id)


def get_project(db: sqlite3.Connection, project_id: str) -> Project | None:
    """Get a project by ID."""
    row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return None
    return _row_to_project(row)


def list_projects(db: sqlite3.Connection) -> list[Project]:
    """List all projects."""
    rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [_row_to_project(r) for r in rows]


def update_project(
    db: sqlite3.Connection,
    project_id: str,
    **kwargs,
) -> Project | None:
    """Update project fields."""
    allowed = {"name", "repo_path", "default_branch", "slack_channel"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return get_project(db, project_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]
    db.execute(
        f"UPDATE projects SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
        values,
    )
    db.commit()
    return get_project(db, project_id)


def ensure_default_project(db: sqlite3.Connection, repo_path: str) -> Project:
    """Ensure a 'default' project exists, creating it if needed."""
    project = get_project(db, "default")
    if not project:
        project = create_project(db, "default", "Default Project", repo_path)
    return project


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        repo_path=row["repo_path"],
        default_branch=row["default_branch"],
        slack_channel=row["slack_channel"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)
