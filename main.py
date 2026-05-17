import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot

api_key = config.DELTA_API_KEY
api_secret = config.DELTA_API_SECRET

print("=" * 50)
print("DELTA AI TRADING BOT")
print("=" * 50)
print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
print(f"Symbol: {config.SYMBOL}")
print("=" * 50)
sys.stdout.flush()

bot = TradingBot(api_key, api_secret)

# Run just one cycle for testing
print("\nRunning single analysis cycle...")
sys.stdout.flush()

analysis = bot.analyze_market()
if analysis:
    print(f"Signal: {analysis['signal']}, Confidence: {analysis['confidence']:.1f}%")
    sys.stdout.flush()
    bot.execute_trade(analysis)

print("\nDone! Bot is working.")
print("To run continuously, change this to call bot.run() instead")