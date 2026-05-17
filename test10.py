# -*- coding: utf-8 -*-
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Step 1: Import config...")
import config
print(f"  Symbol: {config.SYMBOL}")

print("\nStep 2: Import DeltaClient...")
from delta_client import DeltaClient
print("  Done!")

print("\nStep 3: Create client...")
client = DeltaClient("test", "test")
print("  Done!")

print("\nStep 4: Get candles...")
candles = client.get_candles("BTCUSD", "15m", 50)
print(f"  Got {len(candles)} candles")

print("\nStep 5: Import indicators...")
from indicators import TechnicalIndicators
print("  Done!")

print("\nStep 6: Calculate indicators...")
ind = TechnicalIndicators(candles)
data = ind.all_indicators()
print(f"  Price: {data.get('current_price')}")

print("\nStep 7: Import AI...")
from ai_brain import ConfidenceEngine
print("  Done!")

print("\nStep 8: AI analysis...")
ai = ConfidenceEngine()
result = ai.analyze(data, data.get("current_price", 0))
print(f"  Signal: {result.get('signal')}")
print(f"  Confidence: {result.get('confidence')}%")

print("\nAll done!")