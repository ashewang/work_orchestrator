#!/bin/bash
# Start the work orchestrator web dashboard if not already running.
# Used as a Claude Code SessionStart hook.

# Debug: log that this hook ran
echo "[$(date)] start-dashboard.sh fired" >> /tmp/wo-hook-debug.log

PORT=8787

# Check if something is already listening on the port
if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Dashboard already running at http://127.0.0.1:$PORT"
    exit 0
fi

# Start the dashboard in the background
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/../.."
nohup uv run wo ui --no-open >/dev/null 2>&1 &

# Give it a moment to start
sleep 1

if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Dashboard started at http://127.0.0.1:$PORT"
else
    echo "Dashboard is starting up at http://127.0.0.1:$PORT (may take a moment)"
fi

exit 0
