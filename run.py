import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot


def main():
    api_key = config.DELTA_API_KEY
    api_secret = config.DELTA_API_SECRET

    print("=" * 60)
    print("DELTA EXCHANGE AI TRADING BOT - 24/7 AUTOMATED")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE TRADING'}")
    print(f"Symbol: {config.SYMBOL}")
    print(f"Capital: ${config.CAPITAL}")
    print(f"Max Risk/Trade: ${config.MAX_RISK_AMOUNT}")
    print(f"Polling Interval: {config.POLLING_INTERVAL} seconds")
    print("=" * 60)
    print()
    sys.stdout.flush()

    if not api_key or api_key == "YOUR_API_KEY":
        print("WARNING: No API key configured!")
        print("Bot will run but cannot place real orders.")
        print("Set DELTA_API_KEY and DELTA_API_SECRET to enable live trading.")
        print()
        sys.stdout.flush()

    bot = TradingBot(api_key, api_secret)
    bot.run()


if __name__ == "__main__":
    main()