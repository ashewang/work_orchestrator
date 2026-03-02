"""Claude Code agent backend."""

from __future__ import annotations

import json
import shlex
from pathlib import Path


class ClaudeCodeBackend:
    """Backend for Claude Code CLI (claude command)."""

    name = "claude-code"

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
        cmd = ["claude", "-p", prompt, "--output-format", output_format or "json"]
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
        return cmd

    def build_terminal_command(
        self,
        prompt: str,
        model: str | None = None,
        max_turns: int | None = None,
        max_budget: float | None = None,
        permission_mode: str | None = None,
        mcp_config_path: str | None = None,
    ) -> str:
        parts = ["claude", "-p", shlex.quote(prompt)]
        if model:
            parts += ["--model", model]
        if max_budget:
            parts += ["--max-budget-usd", str(max_budget)]
        if permission_mode:
            parts += ["--permission-mode", permission_mode]
        if max_turns:
            parts += ["--max-turns", str(max_turns)]
        if mcp_config_path:
            parts += ["--mcp-config", shlex.quote(mcp_config_path)]
        return " ".join(parts)

    def parse_output(self, output_path: str) -> dict | None:
        path = Path(output_path)
        if not path.exists():
            return None
        content = path.read_text().strip()
        if not content:
            return None
        try:
            data = json.loads(content)
            return {
                "result": data.get("result", content[:500]),
                "exit_code": 0,
            }
        except json.JSONDecodeError:
            return {
                "result": content[:500],
                "exit_code": 1 if "error" in content.lower() else 0,
            }
