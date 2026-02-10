"""Agent orchestration: worktree slot management, agent launching, and monitoring."""

import json
import logging
import os
import shlex
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from work_orchestrator.core.tasks import _log_event, get_task, update_task_status
from work_orchestrator.core.projects import get_project
from work_orchestrator.core.memory import search_memories
from work_orchestrator.db.models import AgentRun, WorktreeSlot
from work_orchestrator.integrations.git import worktree_list

logger = logging.getLogger(__name__)

# Module-level registry of active Popen objects (keyed by PID)
_active_processes: dict[int, subprocess.Popen] = {}


# ── Row-to-model helpers ────────────────────────────────────────────────────


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    return datetime.fromisoformat(val)


def _row_to_slot(row: sqlite3.Row) -> WorktreeSlot:
    return WorktreeSlot(
        id=row["id"],
        project_id=row["project_id"],
        path=row["path"],
        label=row["label"],
        branch=row["branch"],
        status=row["status"],
        current_task_id=row["current_task_id"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_agent_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun(
        id=row["id"],
        task_id=row["task_id"],
        worktree_slot_id=row["worktree_slot_id"],
        pid=row["pid"],
        status=row["status"],
        instructions=row["instructions"],
        model=row["model"],
        max_budget=row["max_budget"],
        output_file=row["output_file"],
        result_summary=row["result_summary"],
        exit_code=row["exit_code"],
        started_at=_parse_dt(row["started_at"]),
        completed_at=_parse_dt(row["completed_at"]),
    )


# ── Worktree Slot Management ────────────────────────────────────────────────


def register_worktree_slot(
    db: sqlite3.Connection,
    project_id: str,
    path: str,
    label: str,
    branch: str | None = None,
) -> WorktreeSlot:
    """Register a single worktree as an available slot."""
    db.execute(
        """INSERT INTO worktree_slots (project_id, path, label, branch)
           VALUES (?, ?, ?, ?)""",
        (project_id, path, label, branch),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM worktree_slots WHERE path = ?", (path,)
    ).fetchone()
    return _row_to_slot(row)


def discover_and_register_worktrees(
    db: sqlite3.Connection,
    project_id: str,
    repo_path: str,
) -> list[WorktreeSlot]:
    """Auto-discover git worktrees for a project and register untracked ones.

    Includes the main repo worktree. Uses directory basename as label.
    """
    project = get_project(db, project_id)
    if not project:
        raise ValueError(f"Project not found: {project_id}")

    git_worktrees = worktree_list(repo_path)

    # Find already-registered paths
    existing = db.execute(
        "SELECT path FROM worktree_slots WHERE project_id = ?", (project_id,)
    ).fetchall()
    existing_paths = {str(Path(r["path"]).resolve()) for r in existing}

    registered = []
    for wt in git_worktrees:
        if wt.is_bare:
            continue
        resolved = str(Path(wt.path).resolve())
        if resolved in existing_paths:
            continue

        label = Path(wt.path).name or project_id
        slot = register_worktree_slot(db, project_id, resolved, label, wt.branch)
        registered.append(slot)

    return registered


def list_worktree_slots(
    db: sqlite3.Connection,
    project_id: str,
    status: str | None = None,
) -> list[WorktreeSlot]:
    """List worktree slots for a project, optionally filtered by status."""
    query = "SELECT * FROM worktree_slots WHERE project_id = ?"
    params: list = [project_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY label"
    rows = db.execute(query, params).fetchall()
    return [_row_to_slot(r) for r in rows]


def get_worktree_slot(db: sqlite3.Connection, slot_id: int) -> WorktreeSlot | None:
    """Get a slot by ID."""
    row = db.execute(
        "SELECT * FROM worktree_slots WHERE id = ?", (slot_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_slot(row)


def get_slot_by_label(
    db: sqlite3.Connection, project_id: str, label: str
) -> WorktreeSlot | None:
    """Get a slot by its label within a project."""
    row = db.execute(
        "SELECT * FROM worktree_slots WHERE project_id = ? AND label = ?",
        (project_id, label),
    ).fetchone()
    if not row:
        return None
    return _row_to_slot(row)


def assign_task_to_slot(
    db: sqlite3.Connection,
    task_id: str,
    slot_id: int,
) -> WorktreeSlot:
    """Assign a task to a worktree slot, marking it occupied."""
    slot = get_worktree_slot(db, slot_id)
    if not slot:
        raise ValueError(f"Slot not found: {slot_id}")
    if slot.status == "occupied":
        raise ValueError(
            f"Slot '{slot.label}' is already occupied by task {slot.current_task_id}"
        )
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    db.execute(
        """UPDATE worktree_slots
           SET status = 'occupied', current_task_id = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (task_id, slot_id),
    )
    db.execute(
        """UPDATE tasks
           SET worktree_path = ?, branch_name = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (slot.path, slot.branch, task_id),
    )
    _log_event(db, task_id, "assigned_to_slot", None, slot.label)
    db.commit()
    return get_worktree_slot(db, slot_id)


def release_slot(db: sqlite3.Connection, slot_id: int) -> WorktreeSlot:
    """Release a worktree slot, marking it available."""
    slot = get_worktree_slot(db, slot_id)
    if not slot:
        raise ValueError(f"Slot not found: {slot_id}")
    db.execute(
        """UPDATE worktree_slots
           SET status = 'available', current_task_id = NULL, updated_at = datetime('now')
           WHERE id = ?""",
        (slot_id,),
    )
    db.commit()
    return get_worktree_slot(db, slot_id)


# ── One-Step Delegation ─────────────────────────────────────────────────────


def delegate_task(
    db: sqlite3.Connection,
    task_id: str,
    instructions: str,
    output_dir: str,
    project_id: str | None = None,
    model: str = "sonnet",
    max_budget: float | None = None,
    max_turns: int = 25,
    permission_mode: str = "acceptEdits",
    slot_label: str | None = None,
    mcp_config_path: str | None = None,
    terminal: bool = False,
) -> AgentRun:
    """One-step delegation: auto-pick available slot, assign task, launch agent.

    If slot_label is provided, uses that specific slot.
    Otherwise, auto-picks the first available slot for the task's project.
    """
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    pid = project_id or task.project_id

    # Fail fast if agent already running
    existing = db.execute(
        "SELECT * FROM agent_runs WHERE task_id = ? AND status = 'running'",
        (task_id,),
    ).fetchone()
    if existing:
        raise ValueError(
            f"Task '{task_id}' already has a running agent (PID {existing['pid']})"
        )

    # Select a slot
    if slot_label:
        slot = get_slot_by_label(db, pid, slot_label)
        if not slot:
            raise ValueError(f"Slot not found: '{slot_label}' in project '{pid}'")
        if slot.status == "occupied":
            raise ValueError(
                f"Slot '{slot_label}' is already occupied by task {slot.current_task_id}"
            )
    else:
        available = list_worktree_slots(db, pid, status="available")
        if not available:
            raise ValueError(
                f"No available worktree slots for project '{pid}'. "
                "Register worktrees first with register_worktrees or 'wo agent register'."
            )
        slot = available[0]

    # Assign the task to the slot
    assign_task_to_slot(db, task_id, slot.id)

    # Auto-resolve MCP config path from project repo
    if not mcp_config_path:
        project = get_project(db, pid)
        if project:
            candidate = Path(project.repo_path) / ".mcp.json"
            if candidate.exists():
                mcp_config_path = str(candidate)

    # Launch the agent
    return launch_agent(
        db, task_id, instructions,
        output_dir=output_dir,
        model=model,
        max_budget=max_budget,
        permission_mode=permission_mode,
        max_turns=max_turns,
        mcp_config_path=mcp_config_path,
        terminal=terminal,
    )


# ── Prompt Construction ──────────────────────────────────────────────────────


def build_agent_prompt(
    db: sqlite3.Connection,
    task_id: str,
    instructions: str,
) -> str:
    """Build a rich prompt for the sub-agent including task context."""
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    project = get_project(db, task.project_id)

    parts = []
    parts.append(f"# Task: {task.title}")
    parts.append(f"Task ID: {task.id}")
    if task.description:
        parts.append(f"\n## Description\n{task.description}")

    if project:
        parts.append(f"\n## Project Context")
        parts.append(f"Project: {project.name} ({project.id})")
        parts.append(f"Repository: {project.repo_path}")
        parts.append(f"Default branch: {project.default_branch}")

    if task.branch_name:
        parts.append(f"Working branch: {task.branch_name}")

    if task.depends_on:
        parts.append(f"\n## Dependencies")
        for dep_id in task.depends_on:
            dep = get_task(db, dep_id)
            if dep:
                parts.append(f"- {dep.title} ({dep.id}): {dep.status}")

    # Pull relevant memories (best-effort)
    try:
        memories = search_memories(db, task.title, project_id=task.project_id)
        if memories:
            parts.append(f"\n## Relevant Context (from memory)")
            for mem in memories[:5]:
                parts.append(f"- **{mem.key}**: {mem.value}")
    except Exception:
        pass

    parts.append(f"\n## Instructions\n{instructions}")

    parts.append(
        "\n## Work Orchestrator Integration\n"
        "You have access to the work-orchestrator MCP tools. Use them to:\n"
        f"- Update your task status: call `update_task_status` with task_id='{task.id}' "
        "and status='in-progress' when you begin.\n"
        "- Store important context: use `remember` to save decisions, blockers, or notes.\n"
        "- Record your PR: use `update_task_pr_url` with the PR URL after creating one.\n"
        "- Check dependencies: use `get_task` to inspect dependent tasks if needed.\n"
        "\n"
        "Do NOT call `launch_agent` or `delegate_task` — you are a subagent, not an orchestrator."
    )

    parts.append(
        "\n## Completion\n"
        "When you are finished, provide a brief summary of what was accomplished, "
        "any files changed, and any issues encountered. "
        "If you created commits, list them. "
        "If you opened a PR, include the URL."
    )

    return "\n".join(parts)


# ── Agent Launching ──────────────────────────────────────────────────────────


def launch_agent(
    db: sqlite3.Connection,
    task_id: str,
    instructions: str,
    output_dir: str,
    model: str = "sonnet",
    max_budget: float | None = None,
    permission_mode: str = "acceptEdits",
    max_turns: int | None = None,
    mcp_config_path: str | None = None,
    terminal: bool = False,
) -> AgentRun:
    """Launch a Claude CLI sub-agent for a task.

    The task must be assigned to a worktree slot.
    If terminal=True, opens the agent in a new Terminal window so you can watch it.
    """
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    # Find the slot for this task
    slot_row = db.execute(
        "SELECT * FROM worktree_slots WHERE current_task_id = ?", (task_id,)
    ).fetchone()
    if not slot_row:
        raise ValueError(
            f"Task '{task_id}' is not assigned to a worktree slot. "
            "Use assign_task first."
        )
    slot = _row_to_slot(slot_row)

    # Check for already-running agent
    existing = db.execute(
        "SELECT * FROM agent_runs WHERE task_id = ? AND status = 'running'",
        (task_id,),
    ).fetchone()
    if existing:
        raise ValueError(
            f"Task '{task_id}' already has a running agent (PID {existing['pid']})"
        )

    # Build the prompt
    prompt = build_agent_prompt(db, task_id, instructions)

    # Prepare output file
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = str(out_path / f"agent-{task_id}-{timestamp}.json")

    # Build command parts (shared between terminal and background modes)
    cmd_parts = ["claude", "-p", shlex.quote(prompt)]
    if model:
        cmd_parts += ["--model", model]
    if max_budget:
        cmd_parts += ["--max-budget-usd", str(max_budget)]
    if permission_mode:
        cmd_parts += ["--permission-mode", permission_mode]
    if max_turns:
        cmd_parts += ["--max-turns", str(max_turns)]
    if mcp_config_path:
        cmd_parts += ["--mcp-config", shlex.quote(mcp_config_path)]

    if terminal:
        pid = _launch_in_terminal(
            cmd_parts, slot.path, output_file, task_id, out_path, timestamp
        )
    else:
        # Background mode: unquote args for direct Popen
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        if max_budget:
            cmd += ["--max-budget-usd", str(max_budget)]
        if permission_mode:
            cmd += ["--permission-mode", permission_mode]
        if max_turns:
            cmd += ["--max-turns", str(max_turns)]
        if mcp_config_path:
            cmd += ["--mcp-config", mcp_config_path]

        with open(output_file, "w") as f:
            proc = subprocess.Popen(
                cmd,
                cwd=slot.path,
                stdout=f,
                stderr=subprocess.STDOUT,
            )
        _active_processes[proc.pid] = proc
        pid = proc.pid

    # Update task status
    if task.status == "todo":
        update_task_status(db, task_id, "in-progress")

    # Record the agent run
    db.execute(
        """INSERT INTO agent_runs
           (task_id, worktree_slot_id, pid, status, instructions, model, max_budget, output_file)
           VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
        (task_id, slot.id, pid, instructions, model, max_budget, output_file),
    )
    _log_event(db, task_id, "agent_launched", None, f"PID {pid}")
    db.commit()

    run_row = db.execute(
        "SELECT * FROM agent_runs WHERE pid = ? AND status = 'running'",
        (pid,),
    ).fetchone()
    return _row_to_agent_run(run_row)


def _launch_in_terminal(
    cmd_parts: list[str],
    cwd: str,
    output_file: str,
    task_id: str,
    out_path: Path,
    timestamp: str,
) -> int:
    """Launch the agent in a visible Terminal window. Returns the PID."""
    pid_file = str(out_path / f"agent-{task_id}-{timestamp}.pid")
    script_file = str(out_path / f"agent-{task_id}-{timestamp}.sh")

    # Build the launcher script
    # Uses tee so output is visible in terminal AND captured to file
    claude_cmd = " ".join(cmd_parts)
    script = (
        "#!/bin/bash\n"
        f"cd {shlex.quote(cwd)}\n"
        f"echo $$ > {shlex.quote(pid_file)}\n"
        f"echo '=== Agent started for task: {task_id} ==='\n"
        f"echo '=== Working in: {cwd} ==='\n"
        f"echo ''\n"
        f"{claude_cmd} 2>&1 | tee {shlex.quote(output_file)}\n"
        f"EXIT_CODE=${{PIPESTATUS[0]}}\n"
        f"echo ''\n"
        f"echo '=== Agent finished (exit code: '$EXIT_CODE') ==='\n"
        f"echo 'Press Enter to close...'\n"
        f"read\n"
    )

    Path(script_file).write_text(script)
    Path(script_file).chmod(0o755)

    # Open in Terminal.app
    subprocess.Popen(["open", "-a", "Terminal", script_file])

    # Wait for the PID file to appear (the script writes it on startup)
    for _ in range(50):
        if Path(pid_file).exists():
            try:
                return int(Path(pid_file).read_text().strip())
            except (ValueError, OSError):
                pass
        time.sleep(0.1)

    # Fallback: return 0 if PID file never appeared
    logger.warning("Could not read PID file for terminal agent %s", task_id)
    return 0


# ── Agent Queries ────────────────────────────────────────────────────────────


def get_agent_run(db: sqlite3.Connection, run_id: int) -> AgentRun | None:
    """Get an agent run by its ID."""
    row = db.execute(
        "SELECT * FROM agent_runs WHERE id = ?", (run_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_agent_run(row)


def get_latest_agent_run(db: sqlite3.Connection, task_id: str) -> AgentRun | None:
    """Get the most recent agent run for a task."""
    row = db.execute(
        "SELECT * FROM agent_runs WHERE task_id = ? ORDER BY started_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_agent_run(row)


def list_agent_runs(
    db: sqlite3.Connection,
    status: str | None = None,
    project_id: str | None = None,
) -> list[AgentRun]:
    """List agent runs, optionally filtered by status and project."""
    if project_id:
        query = """SELECT ar.* FROM agent_runs ar
                   JOIN tasks t ON ar.task_id = t.id
                   WHERE 1=1"""
        params: list = []
        if status:
            query += " AND ar.status = ?"
            params.append(status)
        query += " AND t.project_id = ?"
        params.append(project_id)
    else:
        query = "SELECT * FROM agent_runs WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)

    query += " ORDER BY started_at DESC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_agent_run(r) for r in rows]


def get_agent_output(db: sqlite3.Connection, task_id: str) -> str | None:
    """Read the output file of the latest agent run for a task."""
    run = get_latest_agent_run(db, task_id)
    if not run or not run.output_file:
        return None
    path = Path(run.output_file)
    if not path.exists():
        return None
    return path.read_text()


# ── Agent Cancellation ───────────────────────────────────────────────────────


def cancel_agent(db: sqlite3.Connection, task_id: str) -> AgentRun | None:
    """Cancel a running agent for a task by sending SIGTERM."""
    row = db.execute(
        "SELECT * FROM agent_runs WHERE task_id = ? AND status = 'running' "
        "ORDER BY started_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if not row:
        return None

    run = _row_to_agent_run(row)
    if run.pid:
        try:
            os.kill(run.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Already exited
        _active_processes.pop(run.pid, None)

    db.execute(
        """UPDATE agent_runs
           SET status = 'cancelled', completed_at = datetime('now')
           WHERE id = ?""",
        (run.id,),
    )
    _log_event(db, task_id, "agent_cancelled", f"PID {run.pid}", None)
    db.commit()

    # Release the slot
    if run.worktree_slot_id:
        release_slot(db, run.worktree_slot_id)

    return get_agent_run(db, run.id)


# ── Agent Monitor ────────────────────────────────────────────────────────────


class AgentMonitor:
    """Background thread that monitors running agent processes."""

    def __init__(
        self,
        db_path: Path,
        poll_interval: float = 5.0,
        slack_token: str | None = None,
    ):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.slack_token = slack_token
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        """Start the monitor thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="agent-monitor", daemon=True
        )
        self._thread.start()
        logger.info("Agent monitor started")

    def stop(self):
        """Signal the monitor thread to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Agent monitor stopped")

    def _run(self):
        """Main monitor loop."""
        while not self._stop_event.is_set():
            try:
                self._check_agents()
            except Exception:
                logger.exception("Error in agent monitor loop")
            self._stop_event.wait(self.poll_interval)

    def _check_agents(self):
        """Check all running agents and handle completions."""
        from work_orchestrator.db.engine import init_db

        db = init_db(self.db_path)
        try:
            rows = db.execute(
                "SELECT * FROM agent_runs WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                run = _row_to_agent_run(row)
                proc = _active_processes.get(run.pid)
                if proc is not None:
                    exit_code = proc.poll()
                    if exit_code is None:
                        continue  # Still running
                    _active_processes.pop(run.pid, None)
                    self._handle_completion(db, run, exit_code)
                else:
                    # Orphaned run (server restarted) — check if PID alive
                    if not self._is_pid_alive(run.pid):
                        self._handle_completion(db, run, exit_code=None)
        finally:
            db.close()

    def _is_pid_alive(self, pid: int | None) -> bool:
        """Check if a process is still running."""
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # Process exists but we can't signal it

    def _handle_completion(
        self, db: sqlite3.Connection, run: AgentRun, exit_code: int | None
    ):
        """Handle an agent that has finished running."""
        result_summary = None
        status = "completed"

        if run.output_file and Path(run.output_file).exists():
            try:
                content = Path(run.output_file).read_text()
                if content.strip():
                    try:
                        data = json.loads(content)
                        result_summary = data.get("result", content[:500])
                        if exit_code is None:
                            exit_code = 0
                    except json.JSONDecodeError:
                        result_summary = content[:500]
                        if exit_code is None:
                            exit_code = 1 if "error" in content.lower() else 0
                else:
                    result_summary = "(empty output)"
                    if exit_code is None:
                        exit_code = 1
            except Exception as e:
                result_summary = f"Error reading output: {e}"
                if exit_code is None:
                    exit_code = 1

        if exit_code and exit_code != 0:
            status = "failed"

        db.execute(
            """UPDATE agent_runs
               SET status = ?, exit_code = ?, result_summary = ?,
                   completed_at = datetime('now')
               WHERE id = ?""",
            (status, exit_code, result_summary, run.id),
        )

        # Move task to 'review' (not auto-done — user reviews first)
        if status == "completed":
            update_task_status(db, run.task_id, "review")
            _log_event(db, run.task_id, "agent_completed", None, result_summary)
        else:
            _log_event(db, run.task_id, "agent_failed", None, result_summary)

        # Release the worktree slot
        if run.worktree_slot_id:
            release_slot(db, run.worktree_slot_id)

        db.commit()

        # Send Slack notification (best-effort)
        self._notify_completion(db, run, status, result_summary)

        logger.info(
            "Agent PID %s for task '%s' %s (exit_code=%s)",
            run.pid, run.task_id, status, exit_code,
        )

    def _notify_completion(
        self,
        db: sqlite3.Connection,
        run: AgentRun,
        status: str,
        summary: str | None,
    ):
        """Send a Slack notification for agent completion."""
        if not self.slack_token:
            return
        try:
            from work_orchestrator.integrations.slack import send_message

            task = get_task(db, run.task_id)
            if not task:
                return
            project = get_project(db, task.project_id)
            channel = project.slack_channel if project else None
            if not channel:
                return

            emoji = ":white_check_mark:" if status == "completed" else ":x:"
            text = (
                f"{emoji} Agent {status} for task *{task.title}* (`{task.id}`)\n"
                f"Model: {run.model} | PID: {run.pid}\n"
            )
            if summary:
                text += f"Summary: {summary[:200]}"

            send_message(self.slack_token, channel, text)
        except Exception:
            logger.exception("Failed to send Slack notification for agent completion")
