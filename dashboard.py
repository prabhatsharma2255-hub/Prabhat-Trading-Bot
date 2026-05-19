import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
import requests

st.set_page_config(
    page_title="Trading Bot",
    layout="wide",
    page_icon="\U0001f4c8"
)

IST = timedelta(hours=5, minutes=30)

st.markdown("""
<style>
.stApp { background: #0b0e11; color: white; }
</style>
""", unsafe_allow_html=True)

# FIXED: log_trade function for dashboard
_trade_log = []

def log_trade(direction, entry_price, exit_price, size, pnl, status, confidence=0,
              regime="", signals="", htf_aligned=False, session="", grade="",
              module="", outcome="", leverage=1, stop_loss=0, take_profit=0):
    global _trade_log
    _trade_log.append({
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "size": size,
        "pnl": pnl,
        "status": status,
        "timestamp": datetime.now().isoformat()
    })

def get_live_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=2)
        data = r.json()
        if data and "result" in data:
            return float(data["result"].get("close", 0))
    except:
        return 0
    return 0

def get_bot_trades(max_retries=3):
    for _ in range(max_retries):
        try:
            r = requests.get("http://localhost:5001/api/trades", timeout=3)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        time.sleep(1)
    return {"open": [], "closed": []}

def get_bot_stats(max_retries=3):
    for _ in range(max_retries):
        try:
            r = requests.get("http://localhost:5001/api/stats", timeout=3)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        time.sleep(1)
    return {"total_pnl": 0, "win_rate": 0, "open": 0, "closed": 0}

live_price = get_live_price()
trades = get_bot_trades()
stats = get_bot_stats()

open_trades = trades.get("open", [])
closed_trades = trades.get("closed", [])

col1,col2,col3,col4 = st.columns(4)
col1.metric("BTC Price", f"${live_price:,.0f}" if live_price else "N/A")
col2.metric("Open Trades", stats.get("open", len(open_trades)))
col3.metric("Total PnL", f"${stats.get('total_pnl', 0):.2f}")
col4.metric("Win Rate", f"{stats.get('win_rate', 0):.1f}%")

st.divider()

st.subheader("\U0001f7e2 Open Positions")
if open_trades:
    for t in open_trades:
        entry = t.get("entry_price", 0)
        side = t.get("side", "sell")
        size = t.get("size", 0)
        lev = t.get("leverage", 1)

        if side in ["buy", "long"]:
            pnl = (live_price - entry) * size * lev
        else:
            pnl = (entry - live_price) * size * lev

        pnl_pct = (pnl / (entry * size / lev)) * 100 if (entry * size / lev) > 0 else 0
        color = "green" if pnl >= 0 else "red"
        emoji = "\U0001f7e2" if side in ["buy", "long"] else "\U0001f534"

        st.markdown(f"{emoji} **{side.upper()}** | Entry: ${entry:,.0f} | Mark: ${live_price:,.0f} | <span style='color:{color}'>PnL: ${pnl:.2f} ({pnl_pct:.1f}%)</span> | Size: {size:.4f} | Lev: {lev}x | TP: ${t.get('tp',0):,.0f} | SL: ${t.get('sl',0):,.0f}", unsafe_allow_html=True)
else:
    st.info("No open positions")

st.divider()

st.subheader("\U0001f4cb Closed Trades")
if closed_trades:
    for t in closed_trades:
        pnl = t.get("pnl", 0) or 0
        color = "green" if pnl >= 0 else "red"
        reason = t.get("close_reason", "unknown")
        st.markdown(f"**{t.get('side', 'sell').upper()}** | Entry: ${t.get('entry_price',0):,.0f} | Close: ${t.get('close_price',0):,.0f} | <span style='color:{color}'>PnL: ${pnl:.2f}</span> | {reason}", unsafe_allow_html=True)
else:
    st.info("No closed trades")

st.caption(f"Updated: {datetime.now(IST).strftime('%d/%m %H:%M:%S')} IST | Auto-refresh: 3s")

time.sleep(3)
st.rerun()
