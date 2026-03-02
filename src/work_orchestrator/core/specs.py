"""Spec storage — persist design docs, API specs, and reference material."""

import sqlite3
import uuid
from datetime import datetime

from work_orchestrator.db.models import Spec


def save_spec(
    db: sqlite3.Connection,
    project_id: str,
    title: str,
    content: str,
    source_url: str | None = None,
) -> Spec:
    """Create or update a spec.  If a spec with the same title+project exists, update it."""
    existing = db.execute(
        "SELECT id FROM specs WHERE title = ? AND project_id = ?",
        (title, project_id),
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE specs SET content = ?, source_url = ?, updated_at = datetime('now') WHERE id = ?",
            (content, source_url, existing["id"]),
        )
        db.commit()
        return get_spec(db, existing["id"])
    else:
        spec_id = str(uuid.uuid4())[:8]
        db.execute(
            "INSERT INTO specs (id, project_id, title, content, source_url) VALUES (?, ?, ?, ?, ?)",
            (spec_id, project_id, title, content, source_url),
        )
        db.commit()
        return get_spec(db, spec_id)


def get_spec(db: sqlite3.Connection, spec_id: str) -> Spec | None:
    """Get a spec by ID."""
    row = db.execute("SELECT * FROM specs WHERE id = ?", (spec_id,)).fetchone()
    if not row:
        return None
    return _row_to_spec(row)


def list_specs(
    db: sqlite3.Connection,
    project_id: str | None = None,
) -> list[Spec]:
    """List specs, optionally filtered by project."""
    if project_id:
        rows = db.execute(
            "SELECT * FROM specs WHERE project_id = ? ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM specs ORDER BY updated_at DESC").fetchall()
    return [_row_to_spec(r) for r in rows]


def update_spec(
    db: sqlite3.Connection,
    spec_id: str,
    title: str | None = None,
    content: str | None = None,
) -> Spec | None:
    """Update a spec's title and/or content."""
    spec = get_spec(db, spec_id)
    if not spec:
        return None

    updates = []
    params: list = []
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if content is not None:
        updates.append("content = ?")
        params.append(content)

    if not updates:
        return spec

    updates.append("updated_at = datetime('now')")
    params.append(spec_id)
    db.execute(f"UPDATE specs SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    return get_spec(db, spec_id)


def delete_spec(db: sqlite3.Connection, spec_id: str) -> bool:
    """Delete a spec by ID."""
    result = db.execute("DELETE FROM specs WHERE id = ?", (spec_id,))
    db.commit()
    return result.rowcount > 0


def _row_to_spec(row: sqlite3.Row) -> Spec:
    return Spec(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        content=row["content"],
        source_url=row["source_url"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)
