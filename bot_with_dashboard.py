# Combined Bot + Dashboard Runner
import os
import sys
import threading
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("STARTING AI TRADING BOT + DASHBOARD")
print("=" * 60)

import config
from trading_bot import TradingBot
from dashboard import get_daily_stats, get_all_time_stats
from web_dashboard import app

# Start Flask dashboard in a separate thread
def run_dashboard():
    print("Dashboard will be available at: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Start bot in main thread
def run_bot():
    api_key = config.DELTA_API_KEY
    api_secret = config.DELTA_API_SECRET

    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
    print(f"Symbol: {config.SYMBOL}")
    print(f"Capital: ${config.CAPITAL}")
    print("=" * 60)

    bot = TradingBot(api_key, api_secret)
    bot.run()

if __name__ == "__main__":
    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()

    # Run bot in main thread
    run_bot()