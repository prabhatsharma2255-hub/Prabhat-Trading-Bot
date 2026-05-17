# -*- coding: utf-8 -*-
import os
import sys
import requests

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Testing BTCUSD ticker...")

# Test with correct symbol
r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=10)
print(f"Status: {r.status_code}")
result = r.json()
print(f"Response: {result}")

if result.get("result"):
    ticker = result["result"]
    print(f"\nBTCUSD Price: ${ticker.get('last_price')}")
    print(f"24h High: ${ticker.get('high_24h')}")
    print(f"24h Low: ${ticker.get('low_24h')}")
    print(f"24h Volume: {ticker.get('volume_24h')}")

print("\nDone!")