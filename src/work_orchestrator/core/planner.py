"""CCPM-style planning engine: brainstorm → PRD → task decomposition."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import Generator
from datetime import datetime

import anthropic

from work_orchestrator.core.projects import get_project
from work_orchestrator.core.tasks import create_task, list_tasks, slugify
from work_orchestrator.core.memory import search_memories
from work_orchestrator.db.models import PlanningMessage, PlanningSession

logger = logging.getLogger(__name__)


# ── Row helpers ──────────────────────────────────────────────────────────────


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)


def _row_to_session(row: sqlite3.Row) -> PlanningSession:
    return PlanningSession(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        phase=row["phase"],
        prd_content=row["prd_content"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_message(row: sqlite3.Row) -> PlanningMessage:
    return PlanningMessage(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        created_at=_parse_dt(row["created_at"]),
    )


# ── Session CRUD ─────────────────────────────────────────────────────────────


def create_session(
    db: sqlite3.Connection,
    title: str = "New chat",
    project_id: str | None = None,
) -> PlanningSession:
    """Start a new planning session. project_id is optional."""
    session_id = f"plan-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO planning_sessions (id, project_id, title) VALUES (?, ?, ?)",
        (session_id, project_id, title),
    )
    db.commit()
    return get_session(db, session_id)


def get_session(db: sqlite3.Connection, session_id: str) -> PlanningSession | None:
    row = db.execute(
        "SELECT * FROM planning_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def list_sessions(
    db: sqlite3.Connection, project_id: str | None = None
) -> list[PlanningSession]:
    if project_id:
        rows = db.execute(
            "SELECT * FROM planning_sessions WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM planning_sessions ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_session(r) for r in rows]


def update_session_phase(
    db: sqlite3.Connection, session_id: str, phase: str
) -> PlanningSession | None:
    db.execute(
        "UPDATE planning_sessions SET phase = ?, updated_at = datetime('now') WHERE id = ?",
        (phase, session_id),
    )
    db.commit()
    return get_session(db, session_id)


def update_session_title(
    db: sqlite3.Connection, session_id: str, title: str
) -> PlanningSession | None:
    db.execute(
        "UPDATE planning_sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (title, session_id),
    )
    db.commit()
    return get_session(db, session_id)


def update_session_project(
    db: sqlite3.Connection, session_id: str, project_id: str
) -> PlanningSession | None:
    db.execute(
        "UPDATE planning_sessions SET project_id = ?, updated_at = datetime('now') WHERE id = ?",
        (project_id, session_id),
    )
    db.commit()
    return get_session(db, session_id)


def set_prd_content(
    db: sqlite3.Connection, session_id: str, prd: str
) -> PlanningSession | None:
    db.execute(
        "UPDATE planning_sessions SET prd_content = ?, updated_at = datetime('now') WHERE id = ?",
        (prd, session_id),
    )
    db.commit()
    return get_session(db, session_id)


# ── Message CRUD ─────────────────────────────────────────────────────────────


def add_message(
    db: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
) -> PlanningMessage:
    db.execute(
        "INSERT INTO planning_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM planning_messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return _row_to_message(row)


def get_messages(
    db: sqlite3.Connection, session_id: str
) -> list[PlanningMessage]:
    rows = db.execute(
        "SELECT * FROM planning_messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    return [_row_to_message(r) for r in rows]


# ── System prompts ───────────────────────────────────────────────────────────


def _build_brainstorm_system(
    db: sqlite3.Connection, project_id: str | None
) -> str:
    """Build the system prompt for the brainstorm phase."""
    parts = [
        "You are a technical planning assistant helping decompose project work.",
        "Your role is to ask clarifying questions, explore scope, and help the user define what to build.",
        "",
    ]

    if project_id:
        project = get_project(db, project_id)
        existing_tasks = list_tasks(db, project_id)

        if project:
            parts.append(f"## Project: {project.name}")
            parts.append(f"Repository: {project.repo_path}")
            parts.append(f"Default branch: {project.default_branch}")
            parts.append("")

            # Read project guidelines from .claude
            from work_orchestrator.core.project_context import read_project_context

            pctx = read_project_context(project.repo_path)
            if pctx["project_guidelines"]:
                parts.append(f"## Project Guidelines (from CLAUDE.md)\n{pctx['project_guidelines']}")
                parts.append("")

        if existing_tasks:
            parts.append("## Existing Tasks")
            for t in existing_tasks[:20]:
                deps = f" [depends: {', '.join(t.depends_on)}]" if t.depends_on else ""
                parts.append(f"- [{t.status}] P{t.priority} {t.id}: {t.title}{deps}")
            parts.append("")

        # Pull relevant memories
        try:
            memories = search_memories(db, "architecture design plan", project_id=project_id)
            if memories:
                parts.append("## Project Context (from memory)")
                for mem in memories[:5]:
                    parts.append(f"- **{mem.key}**: {mem.value}")
                parts.append("")
        except Exception:
            pass

    parts.extend([
        "## Guidelines",
        "- Ask 2-3 clarifying questions before jumping to solutions",
        "- Consider existing tasks and how new work fits in",
        "- Think about parallelization opportunities",
        "- When the user says 'looks good' or 'let's write the PRD', generate a structured PRD",
    ])

    return "\n".join(parts)


PRD_GENERATION_PROMPT = """Based on our conversation, generate a structured PRD (Product Requirements Document) in markdown format:

# PRD: {title}

## Vision & Goals
[What we're building and why]

## User Stories
[Key user stories in "As a..., I want..., so that..." format]

## Acceptance Criteria
[Specific, testable criteria for each feature]

## Technical Constraints
[Technology choices, architecture decisions, limitations]

## Out of Scope
[What we're explicitly NOT building in this phase]

## Dependencies & Risks
[External dependencies, potential blockers]

Generate the PRD now based on everything we've discussed."""

DECOMPOSE_PROMPT = """Based on this PRD, decompose the work into concrete tasks.

Return a JSON array of task objects. Each task should have:
- "title": short, action-oriented title
- "description": detailed description with acceptance criteria
- "priority": integer 0-6 (P0 highest, P6 lowest)
- "depends_on": array of task title slugs this depends on (empty array if none)

Guidelines:
- Break into 3-15 tasks (not too granular, not too coarse)
- Order by dependency chain: independent tasks first
- Mark P0-P1 for critical path, P2-P3 for important, P4+ for nice-to-have
- Each task should be completable by one agent in one session

Return ONLY the JSON array, no other text.

PRD:
{prd}"""


# ── Planning Engine ──────────────────────────────────────────────────────────


def plan_message(
    db: sqlite3.Connection,
    session_id: str,
    user_message: str,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Send a message in a planning session and get the assistant's response.

    Returns the full assistant response text.
    """
    session = get_session(db, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    # Store user message
    add_message(db, session_id, "user", user_message)

    # Build conversation for API
    system = _build_brainstorm_system(db, session.project_id)
    messages = get_messages(db, session_id)
    api_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

    # Call Claude API
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=api_messages,
    )

    assistant_text = response.content[0].text

    # Store assistant response
    add_message(db, session_id, "assistant", assistant_text)

    return assistant_text


def plan_message_stream(
    db: sqlite3.Connection,
    session_id: str,
    user_message: str,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> Generator[str, None, None]:
    """Send a message and stream the response token by token.

    Yields text chunks as they arrive. Stores the full response when done.
    """
    session = get_session(db, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    # Store user message
    add_message(db, session_id, "user", user_message)

    # Build conversation
    system = _build_brainstorm_system(db, session.project_id)
    messages = get_messages(db, session_id)
    api_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    full_response = []
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system,
        messages=api_messages,
    ) as stream:
        for text in stream.text_stream:
            full_response.append(text)
            yield text

    # Store the complete response
    add_message(db, session_id, "assistant", "".join(full_response))


def generate_prd(
    db: sqlite3.Connection,
    session_id: str,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Generate a PRD from the brainstorm conversation. Moves session to 'prd' phase.

    Returns the PRD markdown text.
    """
    session = get_session(db, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    title = session.title or "Untitled"
    prd_prompt = PRD_GENERATION_PROMPT.format(title=title)

    # Use plan_message to generate PRD (it stores the message + response)
    prd_text = plan_message(db, session_id, prd_prompt, api_key=api_key, model=model)

    # Store PRD and advance phase
    set_prd_content(db, session_id, prd_text)
    update_session_phase(db, session_id, "prd")

    return prd_text


def decompose_prd(
    db: sqlite3.Connection,
    session_id: str,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """Decompose a PRD into tasks. Moves session to 'decompose' phase.

    Returns the list of task dicts (not yet created in DB).
    """
    session = get_session(db, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    if not session.prd_content:
        raise ValueError("No PRD content to decompose. Generate PRD first.")

    decompose_prompt = DECOMPOSE_PROMPT.format(prd=session.prd_content)

    # Call Claude for decomposition
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system="You are a task decomposition engine. Return ONLY valid JSON arrays.",
        messages=[{"role": "user", "content": decompose_prompt}],
    )

    raw = response.content[0].text.strip()

    # Store the decomposition in messages for reference
    add_message(db, session_id, "system", f"[Decomposition result]\n{raw}")

    # Parse JSON — handle markdown code blocks
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

    tasks = json.loads(raw)
    update_session_phase(db, session_id, "decompose")

    return tasks


def approve_plan(
    db: sqlite3.Connection,
    session_id: str,
    tasks: list[dict],
    project_id: str | None = None,
) -> list:
    """Create tasks in the DB from the decomposed plan. Moves session to 'approved'.

    project_id can be passed explicitly (overrides session's project_id).
    """
    session = get_session(db, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    # Use explicit project_id, fall back to session's, error if neither
    effective_project_id = project_id or session.project_id
    if not effective_project_id:
        raise ValueError("project_id is required to create tasks. Pass it explicitly or set it on the session.")

    # Update session's project_id if it was provided and session didn't have one
    if project_id and not session.project_id:
        update_session_project(db, session_id, project_id)

    created = []
    # Build a map of title → task_id for dependency resolution
    title_to_id: dict[str, str] = {}

    for task_dict in tasks:
        title = task_dict.get("title", "Untitled")
        description = task_dict.get("description", "")
        priority = task_dict.get("priority", 3)

        task = create_task(
            db, title, effective_project_id, description,
            priority=priority,
        )
        title_to_id[slugify(title)] = task.id
        created.append(task)

    # Second pass: add dependencies
    from work_orchestrator.core.tasks import add_dependency
    for i, task_dict in enumerate(tasks):
        deps = task_dict.get("depends_on", [])
        for dep_slug in deps:
            dep_id = title_to_id.get(dep_slug)
            if dep_id and created[i].id != dep_id:
                try:
                    add_dependency(db, created[i].id, dep_id)
                except (ValueError, Exception):
                    pass  # Best-effort dependency linking

    update_session_phase(db, session_id, "approved")
    add_message(db, session_id, "system", f"[Plan approved] Created {len(created)} tasks")

    return created
