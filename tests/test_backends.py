"""Tests for agent backend abstraction."""

import tempfile
import json
from pathlib import Path

import pytest

from work_orchestrator.backends import (
    BACKENDS,
    get_backend,
    list_backends,
    resolve_backend,
)
from work_orchestrator.backends.claude_code import ClaudeCodeBackend
from work_orchestrator.backends.opencode import OpenCodeBackend
from work_orchestrator.backends.pi_agent import PiAgentBackend


class TestRegistry:
    def test_builtin_backends_registered(self):
        assert "claude-code" in BACKENDS
        assert "opencode" in BACKENDS
        assert "pi" in BACKENDS

    def test_list_backends(self):
        names = list_backends()
        assert names == ["claude-code", "opencode", "pi"]

    def test_get_backend(self):
        backend = get_backend("claude-code")
        assert isinstance(backend, ClaudeCodeBackend)

    def test_get_unknown_backend(self):
        with pytest.raises(KeyError, match="Unknown agent backend"):
            get_backend("nonexistent")


class TestResolveBackend:
    def test_task_overrides_all(self):
        backend = resolve_backend("opencode", "pi", "claude-code")
        assert backend.name == "opencode"

    def test_project_overrides_default(self):
        backend = resolve_backend(None, "pi", "claude-code")
        assert backend.name == "pi"

    def test_default_used_as_fallback(self):
        backend = resolve_backend(None, None, "opencode")
        assert backend.name == "opencode"

    def test_hardcoded_fallback(self):
        backend = resolve_backend(None, None, None)
        assert backend.name == "claude-code"


class TestClaudeCodeBackend:
    def setup_method(self):
        self.backend = ClaudeCodeBackend()

    def test_name(self):
        assert self.backend.name == "claude-code"

    def test_build_command_basic(self):
        cmd = self.backend.build_command("Do stuff")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "Do stuff" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_build_command_with_options(self):
        cmd = self.backend.build_command(
            "prompt",
            model="opus",
            max_turns=50,
            max_budget=10.0,
            permission_mode="bypassPermissions",
            mcp_config_path="/path/.mcp.json",
        )
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--max-turns" in cmd
        assert "50" in cmd
        assert "--max-budget-usd" in cmd
        assert "10.0" in cmd
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd
        assert "--mcp-config" in cmd
        assert "/path/.mcp.json" in cmd

    def test_build_terminal_command(self):
        result = self.backend.build_terminal_command("hello world")
        assert "claude" in result
        assert "-p" in result

    def test_parse_output_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"result": "All done!"}, f)
            f.flush()
            parsed = self.backend.parse_output(f.name)
        assert parsed is not None
        assert parsed["result"] == "All done!"
        assert parsed["exit_code"] == 0

    def test_parse_output_plain_text(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("Some plain text output")
            f.flush()
            parsed = self.backend.parse_output(f.name)
        assert parsed is not None
        assert "Some plain text" in parsed["result"]

    def test_parse_output_error_text(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("Error: something went wrong")
            f.flush()
            parsed = self.backend.parse_output(f.name)
        assert parsed["exit_code"] == 1

    def test_parse_output_missing_file(self):
        result = self.backend.parse_output("/nonexistent/path.json")
        assert result is None

    def test_parse_output_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            f.flush()
            result = self.backend.parse_output(f.name)
        assert result is None


class TestOpenCodeBackend:
    def setup_method(self):
        self.backend = OpenCodeBackend()

    def test_name(self):
        assert self.backend.name == "opencode"

    def test_build_command_basic(self):
        cmd = self.backend.build_command("Do stuff")
        assert cmd[0] == "opencode"
        assert "run" in cmd
        assert "Do stuff" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert "--quiet" in cmd

    def test_build_command_with_model(self):
        cmd = self.backend.build_command("prompt", model="gpt-4o")
        assert "--model" in cmd
        assert "gpt-4o" in cmd

    def test_build_terminal_command(self):
        result = self.backend.build_terminal_command("hello")
        assert "opencode" in result
        assert "run" in result


class TestPiAgentBackend:
    def setup_method(self):
        self.backend = PiAgentBackend()

    def test_name(self):
        assert self.backend.name == "pi"

    def test_build_command_basic(self):
        cmd = self.backend.build_command("Do stuff")
        assert cmd[0] == "pi"
        assert "-p" in cmd
        assert "Do stuff" in cmd
        assert "--no-session" in cmd

    def test_build_command_with_model(self):
        cmd = self.backend.build_command("prompt", model="claude-3.5-sonnet")
        assert "--model" in cmd
        assert "claude-3.5-sonnet" in cmd

    def test_build_terminal_command(self):
        result = self.backend.build_terminal_command("hello")
        assert "pi" in result
        assert "--no-session" in result
