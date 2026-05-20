#!/bin/bash
set -e

PORT="${PORT:-5000}"
echo "Starting services on port $PORT..."

# Start bot in background
python run.py &
BOT_PID=$!
echo "Bot PID: $BOT_PID"

# Start dashboard
gunicorn web_dashboard:app --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120 --log-level warning &
FLASK_PID=$!
echo "Dashboard PID: $FLASK_PID"

echo "All running. Bot=$BOT_PID Dashboard=$FLASK_PID"

trap "kill $BOT_PID $FLASK_PID 2>/dev/null; exit" SIGINT SIGTERM
wait