"""
Professional Binance-style Trading Dashboard
Streamlit version with real-time updates
"""
import streamlit as st
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trade_manager import TradeManager
import requests

# Page config
st.set_page_config(
    page_title="Delta Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Auto-refresh every 3 seconds
st_autorefresh = st.empty()
if 'count' not in st.session_state:
    st.session_state.count = 0
st.session_state.count += 1
if st.session_state.count % 1 == 0:
    time.sleep(3)
    st.rerun()

def get_current_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=2)
        data = r.json()
        if data and "result" in data:
            return float(data["result"].get("close", 0))
    except:
        pass
    return 0

def format_duration(open_time: str) -> str:
    """Format duration in human readable format"""
    try:
        if not open_time:
            return "N/A"
        open_dt = datetime.fromisoformat(open_time.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - open_dt
        
        hours = delta.total_seconds() // 3600
        minutes = (delta.total_seconds() % 3600) // 60
        
        if hours > 24:
            days = int(hours // 24)
            return f"{days}d {int(hours%24)}h"
        return f"{int(hours)}h {int(minutes)}m"
    except:
        return "N/A"

def get_close_reason_badge(reason: str) -> str:
    """Get badge emoji for close reason"""
    badges = {
        "tp": "🎯 TP Hit",
        "TP": "🎯 TP Hit",
        "sl": "🛑 SL Hit",
        "SL": "🛑 SL Hit",
        "manual": "✋ Manual",
        "MANUAL": "✋ Manual",
        "MANUAL_CLOSE": "✋ Manual",
        "liquidated": "⚠️ Liquidated",
        "LIQUIDATED": "⚠️ Liquidated"
    }
    return badges.get(reason, reason or "N/A")

# Initialize TradeManager
tm = TradeManager()
current_price = get_current_price()

# Header
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.title("📈 Delta Trading Bot")
with col2:
    st.markdown(f"**BTC/USD:** ${current_price:,.2f}")
with col3:
    status = "🟢 Running" if current_price > 0 else "🔴 Offline"
    st.markdown(f"**Status:** {status}")

st.divider()

# Stats cards
stats = tm.get_stats()

col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    color = "green" if stats['total_pnl'] >= 0 else "red"
    st.metric("Total PnL", f"${stats['total_pnl']:.2f}", delta_color=color)
with col2:
    st.metric("Win Rate", f"{stats['win_rate']:.1f}%")
with col3:
    st.metric("Total Trades", stats['total_trades'])
with col4:
    st.metric("Open Positions", stats['open_positions'])
with col5:
    st.metric("Best Trade", f"${stats['best_trade']:.2f}")
with col6:
    st.metric("Worst Trade", f"${stats['worst_trade']:.2f}")

st.divider()

# Open Positions
st.subheader("📊 Open Positions")
open_trades = tm.get_all_open_trades()

if open_trades:
    open_data = []
    for t in open_trades:
        entry = t.get('entry_price', 0)
        size = t.get('size', 0)
        lev = t.get('leverage', 1)
        side = t.get('side', 'sell')
        
        # Calculate unrealized PnL
        if side in ['buy', 'long']:
            pnl = (current_price - entry) * size * lev
        else:
            pnl = (entry - current_price) * size * lev
        
        pnl_pct = (pnl / (entry * size * lev)) * 100 if (entry * size * lev) > 0 else 0
        
        open_data.append({
            "Symbol": t.get('symbol', 'BTCUSD'),
            "Side": "🟢 LONG" if side in ['buy', 'long'] else "🔴 SHORT",
            "Size": f"{size:.4f}",
            "Leverage": f"{lev}x",
            "Entry": f"${entry:,.0f}",
            "Mark Price": f"${current_price:,.0f}",
            "PnL": f"${pnl:.2f}",
            "PnL %": f"{pnl_pct:.2f}%",
            "Margin": f"${size * entry / lev:,.0f}",
            "TP": f"${t.get('tp', 0):,.0f}" if t.get('tp') else "N/A",
            "SL": f"${t.get('sl', 0):,.0f}" if t.get('sl') else "N/A",
            "Open Time": format_duration(t.get('open_time'))
        })
    
    df = pd.DataFrame(open_data)
    
    # Color styling
    def color_pnl(val):
        if 'PnL' in str(val) and '$' in str(val):
            if '-' in str(val):
                return 'color: red'
            return 'color: green'
        return ''
    
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No open positions")

st.divider()

# Closed Trades
st.subheader("📜 Closed Trades History")
closed_trades = tm.get_all_closed_trades(limit=50)

if closed_trades:
    closed_data = []
    for t in closed_trades:
        entry = t.get('entry_price', 0)
        size = t.get('size', 0)
        lev = t.get('leverage', 1)
        side = t.get('side', 'sell')
        pnl = t.get('pnl', 0) or t.get('pnl_usd', 0)
        entry_usd = entry * size * lev
        pnl_pct = (pnl / entry_usd * 100) if entry_usd > 0 else 0
        
        closed_data.append({
            "#": t.get('trade_id', t.get('id', '')),
            "Symbol": t.get('symbol', 'BTCUSD'),
            "Side": "🟢 LONG" if side in ['buy', 'long'] else "🔴 SHORT",
            "Size": f"{size:.4f}",
            "Leverage": f"{lev}x",
            "Entry": f"${entry:,.0f}",
            "Close": f"${t.get('close_price', 0):,.0f}" if t.get('close_price') else "N/A",
            "PnL": f"${pnl:.2f}",
            "PnL %": f"{pnl_pct:.2f}%",
            "Reason": get_close_reason_badge(t.get('close_reason', '')),
            "Duration": format_duration(t.get('open_time')) + " → " + format_duration(t.get('close_time'))
        })
    
    df = pd.DataFrame(closed_data)
    
    # Pagination
    page = st.number_input("Page", min_value=1, value=1, step=1)
    per_page = 20
    total_pages = len(df) // per_page + (1 if len(df) % per_page else 0)
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    st.dataframe(
        df.iloc[start_idx:end_idx],
        use_container_width=True,
        hide_index=True
    )
    
    st.caption(f"Showing {start_idx+1}-{min(end_idx, len(df))} of {len(df)} trades | Page {page} of {total_pages}")
else:
    st.info("No closed trades yet")

# Footer
st.divider()
st.caption(f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC | Auto-refresh: 3s")