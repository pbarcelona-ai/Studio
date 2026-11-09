#!/usr/bin/env bash
# Simple persistent studio launcher - runs studio.py and opens browser, keeps running until Ctrl+C

cd "$(dirname "$0")" || exit 1   # run from the folder this script lives in

echo "Starting studio.py..."

# Run studio.py and capture its output to extract the URL
PYBIN=python3; [ -x .venv/bin/python ] && PYBIN=.venv/bin/python      # install.sh makes .venv with everything the Studio needs
# --no-open: this script opens the browser itself below (without it studio.py opens a second tab)
: > /tmp/studio_output.txt
"$PYBIN" scripts/studio.py --no-open > >(tee /tmp/studio_output.txt) &
PID=$!

# Give it a moment to start and print the URL
sleep 2

# Extract the URL from output and open it manually on macOS
URL=$(grep -o 'http://127.0.0.1:[0-9]*/?t=[^ ]*' /tmp/studio_output.txt | head -1)
if [[ -n "$URL" ]]; then
    echo "Opening browser: $URL"
    open "$URL"
else
    echo "Could not find URL in output, waiting..."
    sleep 2
    URL=$(grep -o 'http://127.0.0.1:[0-9]*/?t=[^ ]*' /tmp/studio_output.txt | head -1)
    if [[ -n "$URL" ]]; then
        echo "Opening browser: $URL"
        open "$URL"
    else
        echo "ERROR: Could not extract URL from studio.py output"
        cat /tmp/studio_output.txt
    fi
fi

echo ""
echo "Studio is running (PID: $PID)"
echo "Press Ctrl+C to stop"

# Wait for the server process
wait $PID