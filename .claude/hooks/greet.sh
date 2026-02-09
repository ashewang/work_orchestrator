#!/bin/bash
# Gather project state and output a greeting prompt for Claude.
# SessionStart hook — stdout is injected into Claude's context.

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/../.."

# Gather task summary
TASKS=$(uv run wo task list 2>/dev/null)
if [ -z "$TASKS" ]; then
    TASKS="(no tasks found)"
fi

cat <<EOF
=== WORK ORCHESTRATOR SESSION START ===

Current tasks:
$TASKS

IMPORTANT: Before responding to the user's first message, greet them with a short, warm, genuinely funny greeting (2-4 sentences) that references their project state above. Include a quick task summary (done/in-progress/todo counts). Keep it natural — no bullet lists, just a friendly paragraph. Then address whatever they asked.
EOF
