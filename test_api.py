#!/usr/bin/env python3
"""
test_api.py - Delta Exchange India API Diagnostic Tool
"""

import time
import json
import requests
from datetime import datetime

BASE_URL = "https://api.india.delta.exchange"

def test_connection():
    """Test API connectivity and find correct BTC symbol."""
    print("=" * 60)
    print("DELTA EXCHANGE API DIAGNOSTIC TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    results = {
        "api_reachable": False,
        "correct_symbol": None,
        "candles_retrieved": 0,
        "last_candle_time": None,
        "balance": 0.0
    }

    # Test 1: API Reachability
    print("[1/5] Testing API reachability...")
    try:
        response = session.get(BASE_URL + "/v2/tickers/BTCUSD", timeout=10)
        results["api_reachable"] = True
        print(f"    [OK] API is reachable")
        print(f"    Status code: {response.status_code}")
    except Exception as e:
        print(f"    [FAIL] API unreachable: {e}")
        print("=" * 60)
        print("TEST FAILED: Cannot reach API")
        return results

    # Test 2: Find correct BTC perpetual symbol
    print("\n[2/5] Finding correct BTC perpetual symbol...")
    try:
        response = session.get(BASE_URL + "/v2/products", timeout=15)
        if response.status_code == 200:
            products = response.json()
            if "result" in products:
                btc_products = [p for p in products["result"] 
                              if p.get("symbol", "").startswith("BTC") 
                              and p.get("product_type") == "perpetual"]
                
                if btc_products:
                    print(f"    Found {len(btc_products)} BTC perpetual products:")
                    for p in btc_products[:5]:
                        print(f"      - {p.get('symbol')}: {p.get('description', 'N/A')}")
                    
                    results["correct_symbol"] = btc_products[0].get("symbol")
                    print(f"    [OK] Using: {results['correct_symbol']}")
                else:
                    print("    [FAIL] No BTC perpetual products found")
                    print(f"    Response: {json.dumps(products, indent=2)[:500]}")
        else:
            print(f"    [FAIL] Failed to get products: {response.status_code}")
            print(f"    Response: {response.text[:500]}")
    except Exception as e:
        print(f"    [FAIL] Error getting products: {e}")

    # Test 3: Fetch candles with correct symbol
    print("\n[3/5] Fetching candles...")
    symbol = results["correct_symbol"] or "BTCUSD"
    end_time = int(time.time())
    start_time = end_time - (60 * 60 * 24)  # Last 24 hours
    
    # Try different resolution formats
    for resolution in ["15", "15m", "5"]:
        print(f"    Trying resolution: {resolution}")
        url = f"{BASE_URL}/v2/history/candles?symbol={symbol}&resolution={resolution}&start={start_time}&end={end_time}&limit=100"
        print(f"    URL: {url}")
        
        try:
            response = session.get(url, timeout=15)
            print(f"    Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"    Response keys: {data.keys()}")
                
                if "result" in data and data["result"]:
                    candles = data["result"]
                    results["candles_retrieved"] = len(candles)
                    results["last_candle_time"] = candles[-1].get("time") if candles else None
                    
                    if candles:
                        print(f"    [OK] Retrieved {len(candles)} candles")
                        print(f"    First candle: {candles[0]}")
                        print(f"    Last candle: {candles[-1]}")
                        break
                elif "error" in data:
                    print(f"    [FAIL] API error: {data.get('error')}")
                else:
                    print(f"    [FAIL] Empty result, response: {data}")
            else:
                print(f"    [FAIL] Failed: {response.text[:200]}")
        except Exception as e:
            print(f"    [FAIL] Exception: {e}")
    
    # Test 4: Try alternative symbols
    if results["candles_retrieved"] == 0:
        print("\n    Trying alternative symbols...")
        for alt_symbol in ["BTC_USD", "BTC-USD", "BTC_PERP"]:
            print(f"    Trying: {alt_symbol}")
            url = f"{BASE_URL}/v2/history/candles?symbol={alt_symbol}&resolution=15&start={start_time}&end={end_time}&limit=100"
            try:
                response = session.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "result" in data and data["result"]:
                        results["correct_symbol"] = alt_symbol
                        results["candles_retrieved"] = len(data["result"])
                        print(f"    [OK] Worked with {alt_symbol}!")
                        break
            except:
                continue

    # Test 5: Get account balance
    print("\n[4/5] Checking account balance...")
    print("    (Skipping - requires API key authentication)")
    
    # Test 6: Run indicators on fetched data
    print("\n[5/5] Testing indicators on fetched data...")
    if results["candles_retrieved"] > 0:
        try:
            from indicators import TechnicalIndicators
            candles = results.get("test_candles", [])
            if candles:
                ind = TechnicalIndicators(candles)
                all_ind = ind.all_indicators()
                print("    [OK] Indicators calculated successfully:")
                print(f"      RSI: {all_ind.get('rsi', 0):.2f}")
                print(f"      MACD: {all_ind.get('macd', 0):.2f}")
                print(f"      ADX: {all_ind.get('adx', 0):.2f}")
                print(f"      ATR: {all_ind.get('atr', 0):.2f}")
        except Exception as e:
            print(f"    [FAIL] Indicator error: {e}")
    else:
        print("    [FAIL] No candles to test indicators with")

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"API Reachable:        {'YES' if results['api_reachable'] else 'NO'}")
    print(f"Correct Symbol:       {results['correct_symbol'] or 'UNKNOWN'}")
    print(f"Candles Retrieved:    {results['candles_retrieved']}")
    print(f"Last Candle Time:     {results['last_candle_time']}")
    print("=" * 60)

    if results["candles_retrieved"] == 0:
        print("\n*** CRITICAL: No candles retrieved!")
        print("The API endpoint is returning empty data.")
        print("This explains why the bot takes 0 trades.")
    else:
        print("\n[OK] API is working - candles are available")
    
    return results


if __name__ == "__main__":
    test_connection()