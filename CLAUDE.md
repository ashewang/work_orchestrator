# Work Orchestrator

When starting a new conversation in this project, use the `good_morning` MCP prompt to greet the user with a warm, funny, personalized message based on their project state and memories. Do this before anything else.

## Commands

Always use `uv run` to execute Python commands in this project. Never use bare `python`, `pytest`, or `wo` directly.

- Tests: `uv run pytest tests/`
- CLI: `uv run wo <command>`
- Python: `uv run python ...`

## Web Dashboard

The dashboard auto-starts on session launch via a SessionStart hook (port 8787).
If it's not running, start it manually: `uv run wo ui --no-open &`
