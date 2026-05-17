# -*- coding: utf-8 -*-
import os
import sys
import requests

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Finding perpetual contracts...")

r = requests.get("https://api.india.delta.exchange/v2/products", timeout=10)
data = r.json()

# Find perpetual contracts
perpetuals = [p for p in data.get("result", []) if "perpetual" in p.get("symbol", "").lower() or "PERP" in p.get("symbol", "")]
print(f"Found {len(perpetuals)} perpetual contracts:")
for p in perpetuals[:20]:
    print(f"  - {p.get('symbol')} (ID: {p.get('id')})")

# Try to get ticker for perpetuals
print("\nTrying perpetuals:")
for p in perpetuals[:5]:
    sym = p.get('symbol')
    try:
        r = requests.get(f"https://api.india.delta.exchange/v2/tickers/{sym}", timeout=5)
        result = r.json().get("result")
        if result:
            print(f"  {sym}: ${result.get('last_price')}")
    except:
        pass

print("\nDone!")