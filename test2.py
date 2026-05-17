# -*- coding: utf-8 -*-
import os
import sys
import requests

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Finding correct symbol...")

# Get products to find BTC perpetual
r = requests.get("https://api.india.delta.exchange/v2/products", timeout=10)
data = r.json()

btc_products = [p for p in data.get("result", []) if "BTC" in p.get("symbol", "")]
print(f"Found {len(btc_products)} BTC products:")
for p in btc_products[:10]:
    print(f"  - {p.get('symbol')} (ID: {p.get('id')})")

# Try public ticker with symbol
print("\nTrying different symbol formats...")
symbols_to_try = [
    "BTC_USD_PERP",
    "BTC-USD-PERPETUAL",
    "BTCUSD_PERP",
    "BTC_USD",
]

for sym in symbols_to_try:
    try:
        r = requests.get(f"https://api.india.delta.exchange/v2/tickers/{sym}", timeout=5)
        result = r.json().get("result")
        if result:
            print(f"  {sym}: {result.get('last_price')}")
    except:
        pass

print("\nDone!")