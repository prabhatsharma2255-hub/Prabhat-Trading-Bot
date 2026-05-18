#!/bin/bash
# Start both bot and dashboard together

echo "Starting bot and dashboard..."

# Start bot in background
python run.py &
BOT_PID=$!

echo "Bot started with PID: $BOT_PID"

# Wait for bot to fully start (including API)
echo "Waiting for bot to initialize..."
sleep 15

echo "Starting streamlit dashboard..."
streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0