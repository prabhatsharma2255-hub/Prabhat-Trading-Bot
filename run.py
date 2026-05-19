#!/usr/bin/env python3
"""
run.py - 24/7 Trading Bot with Setup-Based System
"""

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot


def main():
    api_key = config.BINANCE_API_KEY
    api_secret = config.BINANCE_API_SECRET

    print("=" * 60)
    print("BINANCE FUTURES AI TRADING BOT - SETUP BASED")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE TRADING'}")
    print(f"Symbol: {config.SYMBOL}")
    print(f"Starting Capital: ${config.STARTING_CAPITAL}")
    print(f"Max Trades/Day: {config.MAX_TRADES_PER_DAY}")
    print(f"Polling Interval: {config.POLLING_INTERVAL}s")
    print("=" * 60)
    print()
    sys.stdout.flush()

    bot = TradingBot(api_key, api_secret)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"\nBot crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()