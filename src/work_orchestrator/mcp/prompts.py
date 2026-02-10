"""MCP prompt templates for common workflows."""

from work_orchestrator.mcp.server import mcp


@mcp.prompt()
def plan_work(goal: str) -> str:
    """Generate a prompt to break down a goal into actionable tasks."""
    return (
        f"I need to accomplish the following goal:\n\n"
        f"{goal}\n\n"
        f"Please break this down into concrete, actionable tasks. For each task:\n"
        f"1. Give it a clear, concise title\n"
        f"2. Add a brief description of what needs to be done\n"
        f"3. Identify dependencies between tasks (which tasks must be done first)\n"
        f"4. Suggest an order of execution\n\n"
        f"Then use the create_task and break_down_task tools to create these tasks in the system."
    )


@mcp.prompt()
def status_report(project: str = "default") -> str:
    """Generate a prompt for a project status report."""
    return (
        f"Please generate a status report for the '{project}' project.\n\n"
        f"Use the list_tasks tool to get all tasks, then provide:\n"
        f"1. Overall progress summary\n"
        f"2. Tasks currently in progress\n"
        f"3. Tasks that are blocked and why\n"
        f"4. Recommended next tasks to work on\n"
        f"5. Any concerns or risks"
    )


@mcp.prompt()
def review_task(task_id: str) -> str:
    """Generate a prompt to review work done in a task."""
    return (
        f"Please review the work done for task '{task_id}'.\n\n"
        f"Use get_task to see task details and worktree_status to check the git status.\n"
        f"Then provide:\n"
        f"1. Summary of changes made\n"
        f"2. Whether the task goals appear to be met\n"
        f"3. Any issues or concerns\n"
        f"4. Whether it's ready to be marked as done"
    )


@mcp.prompt()
def good_morning(project: str = "default") -> str:
    """Generate a warm, funny greeting to start the work session."""
    return (
        f"I just started a work session on the '{project}' project. "
        f"Give me a warm, personalized greeting to get me pumped for work.\n\n"
        f"Please:\n"
        f"1. Use list_tasks to see what I've been working on (in-progress, recently done, what's next)\n"
        f"2. Use search_memories with a broad query like 'preferences' or 'context' to learn about me\n"
        f"3. Use list_tasks with status='todo' to see what's ahead\n\n"
        f"Then write a short, warm, and genuinely funny greeting (2-4 sentences) that:\n"
        f"- References something specific about my project state (what I finished, what's in progress, what's next)\n"
        f"- Has a bit of wit or humor (dad jokes welcome, cringe not)\n"
        f"- Ends with a quick summary: X tasks done, Y in progress, Z ready to go\n"
        f"- Feels like a supportive coworker who actually knows what I'm working on\n\n"
        f"Keep it concise. No bulleted lists. Just a natural, friendly paragraph."
    )


@mcp.prompt()
def dispatch_agents(project: str = "default") -> str:
    """Generate a prompt to dispatch agents to work on ready tasks."""
    return (
        f"I want to dispatch Claude sub-agents to work on tasks in the '{project}' project.\n\n"
        f"Please:\n"
        f"1. Use register_worktrees to ensure worktree slots are registered for '{project}'\n"
        f"2. Use list_slots to see available worktree slots\n"
        f"3. Use get_ready_tasks to find tasks that are ready to start\n"
        f"4. For each ready task (up to the number of available slots):\n"
        f"   - Use delegate_task with detailed instructions for the sub-agent\n"
        f"   - Set max_turns appropriately (25 for simple, 50 for complex tasks)\n"
        f"5. Use list_agents to confirm all agents are running\n"
        f"6. Summarize what was dispatched and which slots remain available"
    )
