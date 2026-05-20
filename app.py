#!/usr/bin/env python3
"""
app.py - Main entry point for Render deployment

Runs both:
1. Trading bot (background thread)
2. Web dashboard (main process)

This is what you deploy to Render.
"""

import os
import sys
import threading
import time
import json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot

bot_thread = None
bot_instance = None


def run_bot():
    """Run trading bot in background."""
    global bot_instance

    api_key = config.BYBIT_API_KEY
    api_secret = config.BYBIT_API_SECRET

    print("=" * 60)
    print("STARTING TRADING BOT")
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
    print("=" * 60)

    bot_instance = TradingBot(api_key, api_secret)
    bot_instance.run()


def main():
    print("=" * 60)
    print("BYBIT TRADING BOT")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
    print(f"Dashboard: http://localhost:{os.environ.get('PORT', 5000)}")
    print("=" * 60)

    global bot_thread

    # Start bot in background
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    time.sleep(3)

    # Import dashboard after bot is initialized
    from web_dashboard import app

    # Share bot instance with dashboard
    app.config["BOT_INSTANCE"] = None

    def set_bot(b):
        app.config["BOT_INSTANCE"] = b

    global bot_instance
    if bot_instance:
        set_bot(bot_instance)

    # Start dashboard
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()