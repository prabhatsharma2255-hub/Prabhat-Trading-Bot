# -*- coding: utf-8 -*-
import os
import sys
import requests

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Testing candles (public endpoint)...")

# Try public candles - may or may not require auth
urls_to_try = [
    "https://api.india.delta.exchange/v2/history/candles?symbol=BTCUSD&resolution=15&limit=50",
    "https://api.india.delta.exchange/v2/candles?symbol=BTCUSD&resolution=15",
]

for url in urls_to_try:
    print(f"\nTrying: {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Status: {r.status_code}")
        result = r.json()
        if result.get("success"):
            candles = result.get("result", [])
            print(f"Got {len(candles)} candles")
            if candles:
                print(f"First candle: {candles[0]}")
        else:
            print(f"Error: {result}")
    except Exception as e:
        print(f"Error: {e}")

print("\nDone!")