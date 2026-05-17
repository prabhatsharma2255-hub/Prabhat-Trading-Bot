# -*- coding: utf-8 -*-
import os
import sys
import requests
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Testing candles with correct params...")

# Get current time and time 1 hour ago
end_time = int(time.time() * 1000)  # milliseconds
start_time = end_time - (60 * 60 * 1000)  # 1 hour ago

url = f"https://api.india.delta.exchange/v2/history/candles?symbol=BTCUSD&resolution=5m&start={start_time}&end={end_time}&limit=100"
print(f"URL: {url[:80]}...")

try:
    r = requests.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    result = r.json()
    if result.get("success"):
        candles = result.get("result", [])
        print(f"Got {len(candles)} candles")
        if candles:
            print(f"First candle: {candles[0]}")
            print(f"Last candle: {candles[-1]}")
    else:
        print(f"Error: {result}")
except Exception as e:
    print(f"Error: {e}")

print("\nDone!")