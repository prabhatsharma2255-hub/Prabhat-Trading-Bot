# -*- coding: utf-8 -*-
import os
import sys
import requests
import json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Searching for futures/perpetuals...")

r = requests.get("https://api.india.delta.exchange/v2/products", timeout=10)
data = r.json()

# Look for all unique product types
product_types = {}
for p in data.get("result", []):
    ptype = p.get("product_type", "unknown")
    if ptype not in product_types:
        product_types[ptype] = []
    product_types[ptype].append(p)

print("Product types found:")
for ptype, products in product_types.items():
    print(f"  {ptype}: {len(products)} products")

# Find any with "BTC" and "USD" that might be futures
print("\nBTC futures:")
for p in data.get("result", []):
    sym = p.get("symbol", "")
    ptype = p.get("product_type", "")
    if "BTC" in sym and "USD" in sym and "CALL" not in sym and "PUT" not in sym:
        print(f"  {sym} (type: {ptype}, id: {p.get('id')})")

# Check a few products in detail
print("\nSample product details:")
for p in data.get("result", [])[:5]:
    print(f"  {json.dumps(p, indent=2)[:200]}")

print("\nDone!")