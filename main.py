#!/usr/bin/env python3
"""
main.py - Delta Exchange Trading Bot
Runs continuously 24/7 on Render
"""

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot


def main():
    api_key = config.DELTA_API_KEY
    api_secret = config.DELTA_API_SECRET

    print("=" * 60)
    print("DELTA AI TRADING BOT - 24/7 CONTINUOUS MODE")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
    print(f"Symbol: {config.SYMBOL}")
    print(f"Poll Interval: {config.POLLING_INTERVAL} seconds")
    print("=" * 60)
    sys.stdout.flush()

    bot = TradingBot(api_key, api_secret)
    
    # Run continuous loop - this runs 24/7
    bot.run()


if __name__ == "__main__":
    main()