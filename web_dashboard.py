#!/usr/bin/env python3
"""
web_dashboard.py - Web Dashboard for Render Deployment

Simple Flask app to display:
- Current bot status
- Open positions
- Recent trades
- Daily stats

Run: python web_dashboard.py
Then access http://localhost:5000
"""

from flask import Flask, render_template_string, jsonify
import sqlite3
from datetime import datetime, timezone, timedelta
import threading
import time
import os
import sys


def get_indian_time():
    """Get current time in Indian Standard Time (UTC+5:30)"""
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = datetime.now(timezone.utc) + ist_offset
    return ist_time.strftime("%Y-%m-%d %H:%M:%S IST")

app = Flask(__name__)

DB_FILE = "trades.db"


def get_current_price():
    """Get current BTC price from Delta API."""
    try:
        import requests
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=5)
        data = r.json()
        if data and "result" in data:
            return float(data["result"].get("close", 0))
    except:
        pass
    return 0


def get_trades(limit=20):
    current_price = get_current_price()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    cols = [desc[0] for desc in c.description]
    trades = []
    for row in c.fetchall():
        trade = dict(zip(cols, row))
        
        if trade["status"] == "open" and current_price > 0:
            if trade["direction"] == "LONG":
                trade["current_pnl"] = (current_price - trade["entry_price"]) * trade["size"]
            else:
                trade["current_pnl"] = (trade["entry_price"] - current_price) * trade["size"]
            trade["current_price"] = current_price
        else:
            trade["current_pnl"] = 0
            trade["current_price"] = 0
            
        trades.append(trade)
    conn.close()
    return trades


def get_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE status = 'closed'")
    total_pnl, total_trades = c.fetchone()
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE date(timestamp_entry) = date('now') AND status = 'closed'")
    daily_pnl, daily_trades = c.fetchone()
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE pnl_usd > 0 AND status = 'closed'")
    wins, win_count = c.fetchone()
    
    c.execute("SELECT * FROM trades WHERE status = 'open'")
    open_trades = c.fetchall()
    
    conn.close()
    
    return {
        "total_pnl": total_pnl or 0,
        "total_trades": total_trades or 0,
        "daily_pnl": daily_pnl or 0,
        "daily_trades": daily_trades or 0,
        "wins": win_count or 0,
        "win_rate": (win_count/total_trades*100) if total_trades and total_trades > 0 else 0,
        "open_positions": len(open_trades)
    }


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Trading Bot</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial; margin: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00ff88; }
        .stats { display: flex; gap: 20px; margin: 20px 0; }
        .stat-box { background: #16213e; padding: 20px; border-radius: 10px; min-width: 150px; }
        .stat-box h3 { margin: 0 0 10px 0; color: #888; }
        .stat-box .value { font-size: 24px; font-weight: bold; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #16213e; }
        tr:hover { background: #16213e; }
        .status-open { color: #00ff88; }
        .status-closed { color: #888; }
        .last-update { color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Delta Exchange AI Trading Bot</h1>
    
    <div class="stats">
        <div class="stat-box">
            <h3>Total PnL</h3>
            <div class="value {{ 'positive' if stats.total_pnl > 0 else 'negative' }}">${{ "%.2f"|format(stats.total_pnl) }}</div>
        </div>
        <div class="stat-box">
            <h3>Daily PnL</h3>
            <div class="value {{ 'positive' if stats.daily_pnl > 0 else 'negative' }}">${{ "%.2f"|format(stats.daily_pnl) }}</div>
        </div>
        <div class="stat-box">
            <h3>Total Trades</h3>
            <div class="value">{{ stats.total_trades }}</div>
        </div>
        <div class="stat-box">
            <h3>Win Rate</h3>
            <div class="value">{{ "%.1f"|format(stats.win_rate) }}%</div>
        </div>
        <div class="stat-box">
            <h3>Open Positions</h3>
            <div class="value">{{ stats.open_positions }}</div>
        </div>
    </div>
    
    <h2>Open Positions</h2>
    <table>
        <tr>
            <th>Direction</th>
            <th>Entry Price</th>
            <th>Current Price</th>
            <th>Size</th>
            <th>PnL</th>
            <th>Regime</th>
            <th>Grade</th>
            <th>Time</th>
        </tr>
        {% for trade in trades if trade.status == 'open' %}
        <tr>
            <td class="{{ 'positive' if trade.direction == 'LONG' else 'negative' }}">{{ trade.direction }}</td>
            <td>${{ "%.2f"|format(trade.entry_price) }}</td>
            <td>${{ "%.2f"|format(trade.current_price) }}</td>
            <td>{{ "%.4f"|format(trade.size) }}</td>
            <td class="{{ 'positive' if trade.current_pnl > 0 else 'negative' }}">${{ "%.2f"|format(trade.current_pnl) }}</td>
            <td>{{ trade.regime }}</td>
            <td>{{ trade.grade }}</td>
            <td>{{ trade.timestamp_entry[:19] if trade.timestamp_entry else 'N/A' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="8">No open positions</td></tr>
        {% endfor %}
    </table>
    
    <h2>Recent Closed Trades</h2>
    <table>
        <tr>
            <th>Direction</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>PnL</th>
            <th>Regime</th>
            <th>Outcome</th>
            <th>Time</th>
        </tr>
        {% for trade in trades if trade.status == 'closed' %}
        <tr>
            <td class="{{ 'positive' if trade.direction == 'LONG' else 'negative' }}">{{ trade.direction }}</td>
            <td>${{ "%.2f"|format(trade.entry_price) }}</td>
            <td>${{ "%.2f"|format(trade.exit_price) }}</td>
            <td class="{{ 'positive' if trade.pnl_usd > 0 else 'negative' }}">${{ "%.2f"|format(trade.pnl_usd) }}</td>
            <td>{{ trade.regime }}</td>
            <td>{{ trade.outcome }}</td>
            <td>{{ trade.timestamp_exit[:19] if trade.timestamp_exit else 'N/A' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="7">No closed trades</td></tr>
        {% endfor %}
    </table>
    
    <div class="last-update">Last updated: {{ last_update }}</div>
</body>
</html>
"""


@app.route('/')
def index():
    stats = get_stats()
    trades = get_trades()
    return render_template_string(HTML_TEMPLATE, stats=stats, trades=trades, last_update=get_indian_time())


@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


@app.route('/api/trades')
def api_trades():
    return jsonify(get_trades(50))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting dashboard on port {port}")
    app.run(host='0.0.0.0', port=port)