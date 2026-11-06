#!/usr/bin/env bash
# Run studio.py for a specified duration then kill it
# Usage: ./run_studio_timed.sh [seconds] [--no-open]  (default: 10 seconds, opens browser)

DURATION=${1:-10}
NO_OPEN=""

# Check for --no-open flag
if [[ "$2" == "--no-open" ]]; then
    NO_OPEN="--no-open"
fi

cd "$(dirname "$0")" || exit 1   # run from the folder this script lives in

echo "Starting studio.py for ${DURATION} seconds..."

# Run studio.py and capture its output to extract the URL
python3 scripts/studio.py $NO_OPEN > >(tee /tmp/studio_output.txt) &
PID=$!

# Give it a moment to start and print the URL
sleep 2

# Extract the URL from output and open it manually on macOS
if [[ -z "$NO_OPEN" ]]; then
    URL=$(grep -o 'http://127.0.0.1:[0-9]*/?t=[^ ]*' /tmp/studio_output.txt | head -1)
    if [[ -n "$URL" ]]; then
        echo "Opening browser: $URL"
        open "$URL"
    fi
fi

sleep $DURATION

echo "Stopping studio.py (PID: $PID)..."
kill $PID 2>/dev/null && echo "Stopped." || echo "Process already exited."