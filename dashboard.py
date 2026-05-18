import streamlit as st
from trade_manager import get_open, get_closed
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
import requests

st.set_page_config(
    page_title="Trading Bot", 
    layout="wide",
    page_icon="📈"
)

IST = timedelta(hours=5, minutes=30)

def to_ist(ts):
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist = dt.astimezone(IST)
        return ist.strftime("%d/%m %H:%M IST")
    except:
        return str(ts)[:19]

def get_live_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=2)
        return float(r.json()["result"]["close"])
    except:
        return 0

st.markdown("""
<style>
.stApp { background: #0b0e11; color: white; }
.profit { color: #0ecb81; }
.loss { color: #f6465d; }
</style>
""", unsafe_allow_html=True)

# Get live price
live_price = get_live_price()

# Stats row
closed = get_closed()
open_t = get_open()
total_pnl = sum(t['pnl'] or 0 for t in closed)
wins = [t for t in closed if (t['pnl'] or 0) > 0]
win_rate = (len(wins)/len(closed)*100) if closed else 0

# Calculate unrealized PnL for open trades
unrealized_pnl = 0
for t in open_t:
    entry = t.get('entry_price', 0)
    size = t.get('size', 0)
    lev = t.get('leverage', 1)
    side = t.get('side', 'sell')
    if side in ['buy', 'long']:
        pnl = (live_price - entry) * size * lev
    else:
        pnl = (entry - live_price) * size * lev
    unrealized_pnl += pnl

col1,col2,col3,col4,col5 = st.columns(5)
col1.metric("BTC Price", f"${live_price:,.0f}")
col2.metric("Unrealized PnL", f"${unrealized_pnl:.2f}")
col3.metric("Total PnL", f"${total_pnl:.2f}")
col4.metric("Open Trades", len(open_t))
col5.metric("Closed Trades", len(closed))

st.divider()

# Open trades with live PnL
st.subheader("🟢 Open Positions")
if open_t:
    for t in open_t:
        entry = t.get('entry_price', 0)
        size = t.get('size', 0)
        lev = t.get('leverage', 1)
        side = t.get('side', 'sell')
        if side in ['buy', 'long']:
            pnl = (live_price - entry) * size * lev
        else:
            pnl = (entry - live_price) * size * lev
        pnl_pct = (pnl / (entry * size / lev)) * 100 if (entry * size / lev) > 0 else 0
        
        color = "green" if pnl >= 0 else "red"
        st.markdown(f"**{t['side'].upper()}** | Entry: ${entry:,.0f} | Mark: ${live_price:,.0f} | <span style='color:{color}'>PnL: ${pnl:.2f} ({pnl_pct:.1f}%)</span> | Size: {size:.4f} | Lev: {lev}x | TP: ${t.get('tp',0):,.0f} | SL: ${t.get('sl',0):,.0f}", unsafe_allow_html=True)
else:
    st.info("No open positions")

# Closed trades - PERMANENT, never disappears
st.subheader("📋 Closed Trades (Full History)")
if closed:
    df2 = pd.DataFrame(closed)
    df2['pnl'] = df2['pnl'].apply(
        lambda x: f"${x:.2f}" if x else "$0.00"
    )
    df2['open_time'] = df2['open_time'].apply(to_ist)
    df2['close_time'] = df2['close_time'].apply(to_ist)
    df2['close_reason'] = df2['close_reason'].map({
        'tp': '🎯 TP Hit',
        'sl': '🛑 SL Hit', 
        'manual': '✋ Manual',
        None: '❓ Unknown'
    }).fillna('❓ Unknown')
    st.dataframe(df2[[
        'symbol','side','size','entry_price',
        'close_price','pnl','close_reason',
        'open_time','close_time'
    ]], use_container_width=True)
else:
    st.info("No closed trades yet")

st.caption(f"Timezone: IST (UTC+5:30) | Last updated: {datetime.now(IST).strftime('%d/%m %H:%M:%S')} IST")

# Auto refresh
time.sleep(3)
st.rerun()