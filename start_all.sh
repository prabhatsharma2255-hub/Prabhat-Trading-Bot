#!/bin/bash
# Start both bot and dashboard together

# Start bot in background
python run.py &
BOT_PID=$!

# Wait for bot to start API
sleep 5

# Start streamlit dashboard
streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0