"""Read .claude context files (CLAUDE.md, user preferences) from a project repo."""

from pathlib import Path

MAX_CONTENT_LEN = 4000


def read_project_context(repo_path: str | Path) -> dict:
    """Read .claude context files from a project repo.

    Returns:
        {
            "project_guidelines": str | None,  # {repo}/CLAUDE.md
            "user_project_notes": str | None,  # {repo}/.claude/CLAUDE.md
            "user_global_prefs": str | None,   # ~/.claude/CLAUDE.md
        }
    """
    repo = Path(repo_path)
    return {
        "project_guidelines": _read_file(repo / "CLAUDE.md"),
        "user_project_notes": _read_file(repo / ".claude" / "CLAUDE.md"),
        "user_global_prefs": _read_file(Path.home() / ".claude" / "CLAUDE.md"),
    }


def _read_file(path: Path) -> str | None:
    """Read a file, returning None if missing. Truncates to MAX_CONTENT_LEN."""
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return None
        if len(content) > MAX_CONTENT_LEN:
            return content[:MAX_CONTENT_LEN] + "\n... (truncated)"
        return content
    except (OSError, UnicodeDecodeError):
        return None
