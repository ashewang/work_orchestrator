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
