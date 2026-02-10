#!/bin/bash
# Gather project state and output a greeting prompt for Claude.
# SessionStart hook — stdout is injected into Claude's context.

# Debug: log that this hook ran
echo "[$(date)] greet.sh fired" >> /tmp/wo-hook-debug.log

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/../.."

# Get user profile via CLI
PROFILE=$(uv run wo profile 2>/dev/null)

# Gather tasks across all projects via CLI
PROJECTS=$(uv run wo projects 2>/dev/null)
TASKS=""
for proj in $PROJECTS; do
    PROJ_TASKS=$(uv run wo task list --project "$proj" 2>/dev/null)
    if [ -n "$PROJ_TASKS" ] && ! echo "$PROJ_TASKS" | grep -q "No tasks found"; then
        TASKS="$TASKS
[$proj]
$PROJ_TASKS
"
    fi
done
if [ -z "$TASKS" ]; then
    TASKS="(no tasks found across any project)"
fi

cat <<EOF
=== WORK ORCHESTRATOR SESSION START ===

Profile:
$PROFILE

Current tasks:
$TASKS

IMPORTANT: Before responding to the user's first message, greet them with a short, warm, genuinely funny greeting (2-4 sentences) that references their project state and profile above. Include a quick task summary (done/in-progress/todo counts). Keep it natural — no bullet lists, just a friendly paragraph. Then address whatever they asked.
EOF
