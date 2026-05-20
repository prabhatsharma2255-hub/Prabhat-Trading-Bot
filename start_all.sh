#!/bin/bash
set -e

PORT="${PORT:-5000}"
BOT_PORT="${BOT_PORT:-5001}"

echo "Starting bot and dashboard on Render..."
echo "PORT=$PORT"

python run.py &
BOT_PID=$!
echo "Bot started with PID: $BOT_PID"

echo "Waiting for bot to initialize..."
sleep 5

echo "Starting Flask web dashboard on port $PORT..."
gunicorn web_dashboard:app --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120 --log-level warning &
FLASK_PID=$!
echo "Flask dashboard started with PID: $FLASK_PID"

echo "All services running. PIDs: Bot=$BOT_PID Flask=$FLASK_PID"

trap "kill $BOT_PID $FLASK_PID 2>/dev/null; exit" SIGINT SIGTERM
wait