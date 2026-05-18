import os
import sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot

bot = TradingBot("test", "test")

print("Running analysis...")
analysis = bot.analyze_market()

if analysis:
    print(f"\nAnalysis returned:")
    print(f"  can_trade: {analysis.get('can_trade')}")
    print(f"  setup: {analysis.get('setup')}")
    print(f"  skip_reason: {analysis.get('skip_reason')}")
    
    if analysis.get("can_trade") and analysis.get("setup"):
        print("\nAttempting to execute trade...")
        result = bot.execute_trade(analysis)
        print(f"Execute result: {result}")
    else:
        print("\nCannot execute - no valid setup")
else:
    print("No analysis returned")