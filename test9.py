# -*- coding: utf-8 -*-
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Testing full bot flow...")

import config
from delta_client import DeltaClient
from indicators import TechnicalIndicators
from ai_brain import ConfidenceEngine

print(f"Symbol: {config.SYMBOL}")

# Create client
client = DeltaClient(config.DELTA_API_KEY, config.DELTA_API_SECRET)

# Get candles
print("\n1. Getting candles...")
candles = client.get_candles(config.SYMBOL, "15m", 100)
print(f"Got {len(candles)} candles")

if candles:
    print(f"Latest close: {candles[-1].get('close')}")

    # Calculate indicators
    print("\n2. Calculating indicators...")
    ind = TechnicalIndicators(candles)
    data = ind.all_indicators()
    print(f"RSI: {data.get('rsi'):.1f}")
    print(f"MACD: {data.get('macd'):.2f}")
    print(f"Price: ${data.get('current_price')}")

    # AI analysis
    print("\n3. AI Analysis...")
    ai = ConfidenceEngine()
    result = ai.analyze(data, data.get("current_price", 0))
    print(f"Regime: {result.get('regime')}")
    print(f"Confidence: {result.get('confidence'):.1f}%")
    print(f"Signal: {result.get('signal')}")
    print(f"Decision: {result.get('decision')}")

print("\nDone!")