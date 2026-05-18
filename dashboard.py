import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="Trading Bot", 
    layout="wide",
    page_icon="📈"
)

IST = timedelta(hours=5, minutes=30)

st.markdown("""
<style>
.stApp { background: #0b0e11; color: white; }
</style>
""", unsafe_allow_html=True)

# Get live price
def get_live_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=2)
        return float(r.json()["result"]["close"])
    except:
        return 0

# Get positions from exchange directly
def get_exchange_positions():
    try:
        import config
        from delta_client import DeltaClient
        client = DeltaClient(config.DELTA_API_KEY, config.DELTA_API_SECRET)
        positions = client.get_positions()
        return positions
    except Exception as e:
        print(f"Error getting positions: {e}")
        return []

# Also try local DB
def get_local_open():
    try:
        from trade_manager import get_open
        return get_open()
    except:
        return []

live_price = get_live_price()
exchange_positions = get_exchange_positions()
local_open = get_local_open()

# Combine positions from both sources
all_open = []

# Add exchange positions
for pos in exchange_positions:
    size = float(pos.get("size", 0))
    if size > 0:
        side = pos.get("side", "sell")
        entry = float(pos.get("avg_price", 0))
        lev = pos.get("leverage", 1)
        
        if side in ["buy", "long"]:
            pnl = (live_price - entry) * abs(size) * lev
        else:
            pnl = (entry - live_price) * abs(size) * lev
        
        all_open.append({
            "source": "exchange",
            "side": side,
            "entry_price": entry,
            "size": abs(size),
            "leverage": lev,
            "pnl": pnl,
            "symbol": "BTCUSD"
        })

# Add local positions
for t in local_open:
    entry = t.get("entry_price", 0)
    size = t.get("size", 0)
    lev = t.get("leverage", 1)
    side = t.get("side", "sell")
    
    if side in ["buy", "long"]:
        pnl = (live_price - entry) * size * lev
    else:
        pnl = (entry - live_price) * size * lev
    
    all_open.append({
        "source": "local",
        "side": side,
        "entry_price": entry,
        "size": size,
        "leverage": lev,
        "pnl": pnl,
        "symbol": t.get("symbol", "BTCUSD"),
        "tp": t.get("tp", 0),
        "sl": t.get("sl", 0)
    })

# Try local DB closed trades
closed = []
try:
    from trade_manager import get_closed
    closed = get_closed()
except:
    pass

total_pnl = sum(t.get('pnl', 0) or 0 for t in closed)
unrealized = sum(p.get("pnl", 0) for p in all_open)

col1,col2,col3,col4 = st.columns(4)
col1.metric("BTC Price", f"${live_price:,.0f}" if live_price else "N/A")
col2.metric("Unrealized PnL", f"${unrealized:.2f}")
col3.metric("Open Positions", len(all_open))
col4.metric("Closed Trades", len(closed))

st.divider()

# Open positions
st.subheader("🟢 Open Positions")
if all_open:
    for p in all_open:
        entry = p.get("entry_price", 0)
        side = p.get("side", "sell")
        size = p.get("size", 0)
        lev = p.get("leverage", 1)
        pnl = p.get("pnl", 0)
        pnl_pct = (pnl / (entry * size / lev)) * 100 if (entry * size / lev) > 0 else 0
        
        color = "green" if pnl >= 0 else "red"
        emoji = "🟢" if side in ["buy", "long"] else "🔴"
        st.markdown(f"{emoji} **{side.upper()}** | Entry: ${entry:,.0f} | Mark: ${live_price:,.0f} | <span style='color:{color}'>PnL: ${pnl:.2f} ({pnl_pct:.1f}%)</span> | Size: {size:.4f} | Lev: {lev}x", unsafe_allow_html=True)
else:
    st.info("No open positions")

st.divider()

# Closed trades
st.subheader("📋 Closed Trades")
if closed:
    for t in closed:
        pnl = t.get("pnl", 0) or 0
        color = "green" if pnl >= 0 else "red"
        reason = t.get("close_reason", "unknown")
        st.markdown(f"**{t.get('side', 'sell').upper()}** | Entry: ${t.get('entry_price',0):,.0f} | Close: ${t.get('close_price',0):,.0f} | <span style='color:{color}'>PnL: ${pnl:.2f}</span> | {reason}", unsafe_allow_html=True)
else:
    st.info("No closed trades")

st.caption(f"Updated: {datetime.now(IST).strftime('%d/%m %H:%M:%S')} IST | Auto-refresh: 3s")

time.sleep(3)
st.rerun()