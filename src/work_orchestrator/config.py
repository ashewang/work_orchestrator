"""Configuration loading from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    db_path: Path = field(default_factory=lambda: Path.home() / ".work_orchestrator" / "wo.db")
    repo_path: Path = field(default_factory=lambda: Path.cwd())
    slack_bot_token: str | None = None
    worktree_dir: str = ".worktrees"
    agent_output_dir: str = ".agent_outputs"
    agent_default_model: str = "sonnet"
    agent_default_budget: float | None = None

    @classmethod
    def from_env(cls) -> "Config":
        config = cls()

        if db := os.environ.get("WO_DB_PATH"):
            config.db_path = Path(db)

        if repo := os.environ.get("WO_REPO_PATH"):
            config.repo_path = Path(repo)

        config.slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")

        if wt_dir := os.environ.get("WO_WORKTREE_DIR"):
            config.worktree_dir = wt_dir

        if out_dir := os.environ.get("WO_AGENT_OUTPUT_DIR"):
            config.agent_output_dir = out_dir

        if model := os.environ.get("WO_AGENT_DEFAULT_MODEL"):
            config.agent_default_model = model

        if budget := os.environ.get("WO_AGENT_DEFAULT_BUDGET"):
            config.agent_default_budget = float(budget)

        return config


def get_config() -> Config:
    return Config.from_env()
