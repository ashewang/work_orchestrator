"""Agent backend abstraction: protocol, registry, and resolution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentBackend(Protocol):
    """Protocol for agent backends (Claude Code, OpenCode, Pi, etc.)."""

    name: str

    def build_command(
        self,
        prompt: str,
        model: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
        permission_mode: str | None = None,
        output_format: str | None = None,
        mcp_config_path: str | None = None,
    ) -> list[str]:
        """Return the full subprocess command list for background mode."""
        ...

    def build_terminal_command(
        self,
        prompt: str,
        model: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
        permission_mode: str | None = None,
        mcp_config_path: str | None = None,
    ) -> str:
        """Return a shell command string for terminal mode (visible in Terminal.app)."""
        ...

    def parse_output(self, output_path: str) -> dict | None:
        """Parse agent output file into structured result."""
        ...


# ── Registry ──────────────────────────────────────────────────────────────────

BACKENDS: dict[str, AgentBackend] = {}


def register_backend(backend: AgentBackend) -> None:
    """Register a backend instance by name."""
    BACKENDS[backend.name] = backend


def get_backend(name: str) -> AgentBackend:
    """Look up a backend by name. Raises KeyError if not found."""
    if name not in BACKENDS:
        available = ", ".join(sorted(BACKENDS.keys())) or "(none)"
        raise KeyError(f"Unknown agent backend: '{name}'. Available: {available}")
    return BACKENDS[name]


def list_backends() -> list[str]:
    """Return sorted list of registered backend names."""
    return sorted(BACKENDS.keys())


def resolve_backend(
    task_backend: str | None,
    project_backend: str | None,
    default_backend: str | None,
) -> AgentBackend:
    """Resolve which backend to use: task → project → env default → claude-code."""
    name = task_backend or project_backend or default_backend or "claude-code"
    return get_backend(name)


# ── Auto-register built-in backends on import ────────────────────────────────

def _register_builtins() -> None:
    from work_orchestrator.backends.claude_code import ClaudeCodeBackend
    from work_orchestrator.backends.opencode import OpenCodeBackend
    from work_orchestrator.backends.pi_agent import PiAgentBackend

    register_backend(ClaudeCodeBackend())
    register_backend(OpenCodeBackend())
    register_backend(PiAgentBackend())


_register_builtins()
