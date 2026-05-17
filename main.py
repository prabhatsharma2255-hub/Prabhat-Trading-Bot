#!/usr/bin/env python3
"""
main.py - Single Cycle Test with Verbose Output

Run this to test a single trading cycle with full diagnostic output.
"""

import os
import sys
import json

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

    print("\n--- Running Market Analysis ---\n")
    sys.stdout.flush()

    analysis = bot.analyze_market()
    
    if analysis:
        print("\n" + "=" * 60)
        print("ANALYSIS RESULTS")
        print("=" * 60)
        
        print(f"Regime:          {analysis.get('regime', 'unknown')}")
        print(f"Module:          {analysis.get('module', 'unknown')}")
        print(f"Signals Fired:   {analysis.get('signals_count', 0)}/5")
        print(f"Signals:         {analysis.get('signals_fired', [])}")
        print(f"Grade:           {analysis.get('grade', 'unknown')}")
        print(f"Direction:       {analysis.get('direction', 'NONE')}")
        print(f"HTF Aligned:     {analysis.get('htf_aligned', False)}")
        print(f"HTF Status:      {analysis.get('htf_status', 'N/A')}")
        print(f"Session:         {analysis.get('session', 'unknown')}")
        print(f"Approved:        {analysis.get('approved', False)}")
        
        if analysis.get("skip_reason"):
            print(f"Skip Reason:     {analysis.get('skip_reason')}")
        
        print(f"\nEntry Details:")
        print(f"  Price:         ${analysis.get('current_price', 0):.2f}")
        print(f"  Stop Loss:     ${analysis.get('stop_loss', 0):.2f}")
        print(f"  TP1:           ${analysis.get('take_profit_1', 0):.2f}")
        print(f"  TP2:           ${analysis.get('take_profit_2', 0):.2f}")
        print(f"  TP3:           ${analysis.get('take_profit_3', 0):.2f}")
        print(f"  Leverage:      {analysis.get('leverage', 1)}x")
        print(f"  Risk %:        {analysis.get('risk_pct', 0)*100}%")
        
        ltf = analysis.get("ltf_indicators", {})
        print(f"\nLTF Indicators:")
        print(f"  RSI:           {ltf.get('rsi', 0):.2f}")
        print(f"  MACD:          {ltf.get('macd', 0):.4f}")
        print(f"  MACD Hist:     {ltf.get('macd_histogram', 0):.4f}")
        print(f"  ADX:           {ltf.get('adx', 0):.2f} ({ltf.get('adx_strength', 'N/A')})")
        print(f"  +DI:           {ltf.get('plus_di', 0):.2f}")
        print(f"  -DI:           {ltf.get('minus_di', 0):.2f}")
        print(f"  ATR:           {ltf.get('atr', 0):.2f}")
        print(f"  ATR %:         {ltf.get('atr_pct', 0):.2f}%")
        print(f"  BB Width:      {ltf.get('bb_width', 0):.2f}%")
        print(f"  Supertrend:    {ltf.get('supertrend', 'N/A')}")
        print(f"  Volume Ratio:  {ltf.get('volume_ratio', 1):.2f}")
        
        htf = analysis.get("htf_indicators", {})
        if htf:
            print(f"\nHTF Indicators (1h):")
            print(f"  EMA50:         ${htf.get('ema_50', 0):.2f}")
            print(f"  EMA50 Prev:    ${htf.get('ema_50_prev', 0):.2f}")
            print(f"  ADX:           {htf.get('adx', 0):.2f}")
        
        print("=" * 60)
        
        if analysis.get("approved"):
            print("\n>>> Attempting to execute trade...")
            sys.stdout.flush()
            result = bot.execute_trade(analysis)
            if result:
                print(">>> Trade EXECUTED successfully!")
            else:
                print(">>> Trade execution FAILED")
        else:
            print("\n>>> Trade NOT approved - see skip reason above")
        
    else:
        print("\n!!! No analysis returned - check API connection")

    stats = bot.risk_manager.get_stats()
    print(f"\nRisk Manager Stats:")
    print(f"  Balance:       ${stats['balance']:.2f}")
    print(f"  Peak:          ${stats['peak_balance']:.2f}")
    print(f"  Drawdown:      {stats['drawdown_pct']:.1f}%")
    print(f"  Total Trades:  {stats['total_trades']}")
    print(f"  Win Rate:      {stats['win_rate']:.1f}%")
    print(f"  Review Mode:   {stats['review_mode']}")

    print("\nDone! Bot test complete.")


if __name__ == "__main__":
    main()