# -*- coding: utf-8 -*-
import os
import sys
import requests

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Testing Delta API connection...")
print("=" * 50)

# Test 1: Public API (no auth)
print("\n1. Testing public ticker API...")
try:
    r = requests.get("https://api.india.delta.exchange/v2/tickers/BTC-USD-PERPETUAL", timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Products API
print("\n2. Testing products API...")
try:
    r = requests.get("https://api.india.delta.exchange/v2/products", timeout=5)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Products count: {len(data.get('result', []))}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 50)
print("Basic tests done. Now testing with auth...")

import config
print(f"API Key: {config.DELTA_API_KEY[:15]}...")

from delta_client import DeltaClient

client = DeltaClient(config.DELTA_API_KEY, config.DELTA_API_SECRET)

print("\n3. Testing authenticated ticker...")
ticker = client.get_ticker(config.SYMBOL)
print(f"Result: {ticker}")

print("\nDone!")