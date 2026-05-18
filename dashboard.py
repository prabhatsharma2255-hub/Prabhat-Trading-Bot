import streamlit as st
from trade_manager import get_open, get_closed
import pandas as pd
import time

st.set_page_config(
    page_title="Trading Bot", 
    layout="wide",
    page_icon="📈"
)

st.markdown("""
<style>
.stApp { background: #0b0e11; color: white; }
.profit { color: #0ecb81; }
.loss { color: #f6465d; }
</style>
""", unsafe_allow_html=True)

# Stats row
closed = get_closed()
open_t = get_open()
total_pnl = sum(t['pnl'] or 0 for t in closed)
wins = [t for t in closed if (t['pnl'] or 0) > 0]
win_rate = (len(wins)/len(closed)*100) if closed else 0

col1,col2,col3,col4 = st.columns(4)
col1.metric("Total PnL", f"${total_pnl:.2f}")
col2.metric("Win Rate", f"{win_rate:.1f}%")
col3.metric("Open Trades", len(open_t))
col4.metric("Closed Trades", len(closed))

st.divider()

# Open trades
st.subheader("🟢 Open Positions")
if open_t:
    df = pd.DataFrame(open_t)
    st.dataframe(df[[
        'symbol','side','size','entry_price',
        'tp','sl','leverage','open_time'
    ]], use_container_width=True)
else:
    st.info("No open positions")

# Closed trades - PERMANENT, never disappears
st.subheader("📋 Closed Trades (Full History)")
if closed:
    df2 = pd.DataFrame(closed)
    df2['pnl'] = df2['pnl'].apply(
        lambda x: f"${x:.2f}" if x else "$0.00"
    )
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

# Auto refresh
time.sleep(3)
st.rerun()