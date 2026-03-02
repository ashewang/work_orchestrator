"""SQLite database connection management and schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    default_branch TEXT DEFAULT 'main',
    slack_channel TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'todo' CHECK (status IN ('todo', 'in-progress', 'done', 'blocked', 'review')),
    priority INTEGER DEFAULT 3,
    parent_task_id TEXT REFERENCES tasks(id),
    branch_name TEXT,
    worktree_path TEXT,
    pr_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    project_id TEXT REFERENCES projects(id),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(key, project_id)
);

CREATE TABLE IF NOT EXISTS specs (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS worktree_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    path TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    branch TEXT,
    status TEXT DEFAULT 'available' CHECK (status IN ('available', 'occupied')),
    current_task_id TEXT REFERENCES tasks(id),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    worktree_slot_id INTEGER REFERENCES worktree_slots(id),
    pid INTEGER,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    instructions TEXT NOT NULL,
    model TEXT DEFAULT 'sonnet',
    max_budget REAL,
    output_file TEXT,
    result_summary TEXT,
    exit_code INTEGER,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS planning_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id),
    title TEXT,
    phase TEXT DEFAULT 'brainstorm' CHECK (phase IN ('brainstorm', 'prd', 'decompose', 'approved', 'cancelled')),
    prd_content TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS planning_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES planning_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    key, value, category, content=memories, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, key, value, category)
    VALUES (new.id, new.key, new.value, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, key, value, category)
    VALUES ('delete', old.id, old.key, old.value, old.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, key, value, category)
    VALUES ('delete', old.id, old.key, old.value, old.category);
    INSERT INTO memories_fts(rowid, key, value, category)
    VALUES (new.id, new.key, new.value, new.category);
END;
"""


def _run_migrations(conn: sqlite3.Connection):
    """Run schema migrations idempotently."""
    migrations = [
        "ALTER TABLE tasks ADD COLUMN pr_url TEXT",
        "ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 3",
        # Multi-backend support
        "ALTER TABLE projects ADD COLUMN agent_backend TEXT",
        "ALTER TABLE tasks ADD COLUMN agent_backend TEXT",
        "ALTER TABLE agent_runs ADD COLUMN backend TEXT DEFAULT 'claude-code'",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Migrate CHECK constraint to include 'review' status
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='tasks' AND type='table'"
    ).fetchone()
    if table_sql and "'review'" not in table_sql[0]:
        new_sql = table_sql[0].replace(
            "('todo', 'in-progress', 'done', 'blocked')",
            "('todo', 'in-progress', 'done', 'blocked', 'review')",
        )
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute(
            "UPDATE sqlite_master SET sql=? WHERE name='tasks' AND type='table'",
            (new_sql,),
        )
        conn.execute("PRAGMA writable_schema=OFF")

    # Migrate worktree_slots CHECK constraint to include 'draining'
    slot_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='worktree_slots' AND type='table'"
    ).fetchone()
    if slot_sql and "'draining'" not in slot_sql[0]:
        new_sql = slot_sql[0].replace(
            "('available', 'occupied')",
            "('available', 'occupied', 'draining')",
        )
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute(
            "UPDATE sqlite_master SET sql=? WHERE name='worktree_slots' AND type='table'",
            (new_sql,),
        )
        conn.execute("PRAGMA writable_schema=OFF")

    conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the database, creating tables if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.executescript(FTS_SCHEMA)
    _run_migrations(conn)
    conn.commit()
    return conn


@contextmanager
def get_db(db_path: Path):
    """Context manager for database connections."""
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()
