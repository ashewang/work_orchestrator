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

When the user asks you to delegate work to subagents, use the `delegate_task` MCP tool. It auto-creates a git worktree and launches an agent in a separate Terminal window.

### IMPORTANT: Do NOT explore the target repo before delegating.

The subagent gets the project's CLAUDE.md context and has full access to the codebase in its worktree. It can explore the repo itself. Your job is to write clear instructions and call `delegate_task` immediately. Do not use Explore, Grep, Read, or any other tool to look at the target project's code before delegating.

### Delegation workflow:
1. Call `delegate_task` with:
   - `task_id`: the task to work on
   - `instructions`: detailed instructions describing what to build/fix and acceptance criteria
   - `max_turns`: 50 for typical tasks, 100 for complex multi-file changes
   - `model`: "sonnet" for most tasks, "opus" for architecture/complex reasoning
2. The subagent opens in a new Terminal window — it does NOT block this conversation
3. Monitor progress: call `agent_status` or `list_agents` to check

### Writing good agent instructions:
- Describe WHAT to build and the acceptance criteria
- Do NOT pre-research the codebase to figure out HOW — let the subagent do that
- Include any user-provided context or requirements verbatim
- Do NOT include instructions to update task status — the agent prompt handles this automatically

### Checking results:
- `agent_status` shows if agents are running/completed/failed
- `get_agent_output` shows the captured output after completion
- Completed agents automatically create a PR and store the URL on the task

## Web Dashboard

The dashboard auto-starts on session launch via a SessionStart hook (port 8787).
If it's not running, start it manually: `uv run wo ui --no-open &`
