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

## Agent Delegation

When the user asks you to delegate work to subagents, use the `delegate_task` MCP tool. This combines slot assignment and agent launch into one step.

### Delegation workflow:
1. Ensure worktree slots are registered: call `register_worktrees` for the project
2. Identify ready tasks: call `get_ready_tasks` for the project
3. For each task to delegate: call `delegate_task` with:
   - `task_id`: the task to work on
   - `instructions`: detailed, specific instructions for the subagent (include acceptance criteria)
   - `max_turns`: 25 for typical tasks, 50+ for complex multi-file changes
   - `model`: "sonnet" for most tasks, "opus" for architecture/complex reasoning
4. Monitor progress: call `agent_status` or `list_agents` to check

### Writing good agent instructions:
- Be specific about what files to change and what the expected behavior is
- Include acceptance criteria (tests to pass, behavior to verify)
- Mention the branch they are on and any relevant context
- Do NOT include instructions to update task status — the agent prompt handles this automatically

### Checking results:
- `agent_status` shows if agents are running/completed/failed
- `get_agent_output` shows the captured output after completion
- Completed agents automatically move tasks to "review" status

## Web Dashboard

The dashboard auto-starts on session launch via a SessionStart hook (port 8787).
If it's not running, start it manually: `uv run wo ui --no-open &`
