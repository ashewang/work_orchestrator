# Work Orchestrator

When starting a new conversation in this project, greet the user before anything else.

To do this:
1. Use the `list_tasks` MCP tool to see what's in-progress, recently done, and upcoming
2. Use the `search_memories` MCP tool with a broad query like "preferences" or "context" to learn about the user
3. Use `list_tasks` with status='todo' to see what's ahead

Then write a short, warm, and genuinely funny greeting (2-4 sentences) that:
- References something specific about the project state (what was finished, what's in progress, what's next)
- Has a bit of wit or humor (dad jokes welcome, cringe not)
- Ends with a quick summary: X tasks done, Y in progress, Z ready to go
- Feels like a supportive coworker who actually knows what they're working on

Keep it concise. No bulleted lists. Just a natural, friendly paragraph.

## Commands

Always use `uv run` to execute Python commands in this project. Never use bare `python`, `pytest`, or `wo` directly.

- Tests: `uv run pytest tests/`
- CLI: `uv run wo <command>`
- Python: `uv run python ...`

## Web Dashboard

The dashboard auto-starts on session launch via a SessionStart hook (port 8787).
If it's not running, start it manually: `uv run wo ui --no-open &`
