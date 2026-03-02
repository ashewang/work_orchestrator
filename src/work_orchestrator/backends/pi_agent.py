"""Pi agent backend."""

from __future__ import annotations

import json
import shlex
from pathlib import Path


class PiAgentBackend:
    """Backend for Pi CLI (pi command)."""

    name = "pi"

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
        cmd = ["pi", "-p", prompt, "--no-session"]
        if model:
            cmd += ["--model", model]
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
        parts = ["pi", "-p", shlex.quote(prompt), "--no-session"]
        if model:
            parts += ["--model", model]
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
