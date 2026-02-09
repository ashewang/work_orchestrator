"""Persistent memory/context store with full-text search."""

import sqlite3
from datetime import datetime

from work_orchestrator.db.models import Memory


def remember(
    db: sqlite3.Connection,
    key: str,
    value: str,
    category: str = "general",
    project_id: str | None = None,
) -> Memory:
    """Store or update a memory entry."""
    existing = db.execute(
        "SELECT id FROM memories WHERE key = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
        (key, project_id, project_id),
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE memories SET value = ?, category = ?, updated_at = datetime('now') WHERE id = ?",
            (value, category, existing["id"]),
        )
        db.commit()
        return recall_by_key(db, key, project_id)
    else:
        db.execute(
            "INSERT INTO memories (key, value, category, project_id) VALUES (?, ?, ?, ?)",
            (key, value, category, project_id),
        )
        db.commit()
        return recall_by_key(db, key, project_id)


def recall_by_key(
    db: sqlite3.Connection,
    key: str,
    project_id: str | None = None,
) -> Memory | None:
    """Retrieve a memory by exact key."""
    row = db.execute(
        "SELECT * FROM memories WHERE key = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
        (key, project_id, project_id),
    ).fetchone()
    if not row:
        return None
    return _row_to_memory(row)


def search_memories(
    db: sqlite3.Connection,
    query: str,
    category: str | None = None,
    project_id: str | None = None,
) -> list[Memory]:
    """Full-text search across memories."""
    sql = """
        SELECT m.* FROM memories m
        JOIN memories_fts fts ON m.id = fts.rowid
        WHERE memories_fts MATCH ?
    """
    params: list = [query]

    if category:
        sql += " AND m.category = ?"
        params.append(category)

    if project_id is not None:
        sql += " AND m.project_id = ?"
        params.append(project_id)

    sql += " ORDER BY rank"
    rows = db.execute(sql, params).fetchall()
    return [_row_to_memory(r) for r in rows]


def list_memories(
    db: sqlite3.Connection,
    category: str | None = None,
    project_id: str | None = None,
) -> list[Memory]:
    """List memories, optionally filtered by category and project."""
    sql = "SELECT * FROM memories WHERE 1=1"
    params: list = []

    if category:
        sql += " AND category = ?"
        params.append(category)

    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)

    sql += " ORDER BY updated_at DESC"
    rows = db.execute(sql, params).fetchall()
    return [_row_to_memory(r) for r in rows]


def forget(db: sqlite3.Connection, key: str, project_id: str | None = None) -> bool:
    """Delete a memory entry by key."""
    result = db.execute(
        "DELETE FROM memories WHERE key = ? AND (project_id = ? OR (project_id IS NULL AND ? IS NULL))",
        (key, project_id, project_id),
    )
    db.commit()
    return result.rowcount > 0


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        key=row["key"],
        value=row["value"],
        category=row["category"],
        project_id=row["project_id"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)
