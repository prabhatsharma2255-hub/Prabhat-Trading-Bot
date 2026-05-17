#!/usr/bin/env python3
"""
main.py - Single Cycle Test with Setup-Based System
"""

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config
from trading_bot import TradingBot


def main():
    api_key = config.DELTA_API_KEY
    api_secret = config.DELTA_API_SECRET

    print("=" * 60)
    print("DELTA AI TRADING BOT - SINGLE CYCLE TEST")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
    print(f"Symbol: {config.SYMBOL}")
    print("=" * 60)
    sys.stdout.flush()

    bot = TradingBot(api_key, api_secret)

    intel = bot.get_market_intelligence()
    print(f"\n--- MARKET INTELLIGENCE ---")
    print(f"Sentiment: {intel['sentiment']} ({intel['composite']:.1f})")
    print(f"Fear & Greed: {intel['fear_greed']}")
    print(f"Funding: {intel['funding_rate']:.4f}% ({intel['funding_bias']})")
    print(f"Velocity: 1m={intel['velocity_1m']:.2f}% | 3m={intel['velocity_3m']:.2f}%")
    print(f"Whale: {intel['whale_event']} | Urgent: {intel['urgent_event']}")

    print("\n--- Running Market Analysis ---\n")
    sys.stdout.flush()

    analysis = bot.analyze_market()
    
    print("\n" + "=" * 60)
    print("Done! Bot test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()