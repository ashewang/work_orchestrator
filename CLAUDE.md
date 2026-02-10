# Work Orchestrator

## MANDATORY: Session Greeting

Your FIRST response in EVERY new conversation MUST start with a personalized greeting paragraph. This is non-negotiable.

A SessionStart hook injects task state into your context (look for "=== WORK ORCHESTRATOR SESSION START ===" in your context). Use that data to write a short (2-4 sentence), warm, funny greeting that mentions their project progress. Then handle their request after the greeting.

## MCP Tools

The `list_tasks` tool defaults to `project="default"`, which is usually empty. Always call `list_projects` first to discover actual project IDs, then pass those IDs to `list_tasks`, `get_ready_tasks`, etc.

## Commands

Always use `uv run` to execute Python commands in this project. Never use bare `python`, `pytest`, or `wo` directly.

- Tests: `uv run pytest tests/`
- CLI: `uv run wo <command>`
- Python: `uv run python ...`

## Web Dashboard

The dashboard auto-starts on session launch via a SessionStart hook (port 8787).
If it's not running, start it manually: `uv run wo ui --no-open &`
