"""Data models for work orchestrator."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Project:
    id: str
    name: str
    repo_path: str
    default_branch: str = "main"
    slack_channel: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Task:
    id: str
    project_id: str
    title: str
    description: str = ""
    status: str = "todo"
    priority: int = 3
    parent_task_id: str | None = None
    branch_name: str | None = None
    worktree_path: str | None = None
    pr_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    depends_on: list[str] = field(default_factory=list)
    subtasks: list["Task"] = field(default_factory=list)


@dataclass
class Memory:
    id: int | None = None
    key: str = ""
    value: str = ""
    category: str = "general"
    project_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class TaskEvent:
    id: int | None = None
    task_id: str = ""
    event_type: str = ""
    old_value: str | None = None
    new_value: str | None = None
    created_at: datetime | None = None


@dataclass
class WorktreeSlot:
    id: int | None = None
    project_id: str = ""
    path: str = ""
    label: str = ""
    branch: str | None = None
    status: str = "available"
    current_task_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class AgentRun:
    id: int | None = None
    task_id: str = ""
    worktree_slot_id: int | None = None
    pid: int | None = None
    status: str = "running"
    instructions: str = ""
    model: str = "sonnet"
    max_budget: float | None = None
    output_file: str | None = None
    result_summary: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
