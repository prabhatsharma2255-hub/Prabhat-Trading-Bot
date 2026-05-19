#!/bin/bash
# Start both bot and dashboard together
# Works locally and on Render (PORT env var set by Render)

set -e

PORT="${PORT:-5000}"
BOT_PORT="${BOT_PORT:-5001}"

echo "Starting bot and dashboard on Render..."
echo "PORT=$PORT"

# Start bot in background
python run.py &
BOT_PID=$!
echo "Bot started with PID: $BOT_PID"

# Wait for bot to initialize
echo "Waiting for bot to initialize..."
sleep 10

echo "Starting Flask web dashboard (WebSocket) on port $PORT..."
gunicorn web_dashboard:app --bind 0.0.0.0:$PORT --worker-class eventlet --workers 1 --timeout 120 --log-level info &
FLASK_PID=$!
echo "Flask dashboard started with PID: $FLASK_PID"

echo "Also starting Streamlit dashboard on port $BOT_PORT..."
streamlit run dashboard.py --server.port $BOT_PORT --server.address 0.0.0.0 &
STREAMLIT_PID=$!
echo "Streamlit dashboard started with PID: $STREAMLIT_PID"

echo "All services running. PIDs: Bot=$BOT_PID Flask=$FLASK_PID Streamlit=$STREAMLIT_PID"

# Trap exit to kill children
trap "kill $BOT_PID $FLASK_PID $STREAMLIT_PID 2>/dev/null; exit" SIGINT SIGTERM

# Wait for any child to exit
wait