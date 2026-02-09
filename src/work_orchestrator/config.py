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

        return config


def get_config() -> Config:
    return Config.from_env()
