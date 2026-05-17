import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("1. About to import config...")
sys.stdout.flush()

import config
print("2. Config imported")

from trading_bot import TradingBot
print("3. TradingBot imported")

print("4. Creating bot...")
bot = TradingBot("test", "test")
print("5. Bot created!")

print("6. Getting candles...")
candles = bot.get_market_data("15m", 20)
print(f"   Got {len(candles)} candles")

print("7. Analyzing...")
result = bot.analyze_market()
print(f"   Result: {result['signal']}")

print("\nAll OK!")