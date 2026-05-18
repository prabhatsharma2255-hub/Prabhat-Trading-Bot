#!/usr/bin/env python3
"""
web_dashboard.py - Enhanced Web Dashboard for Trading Bot
"""

from flask import Flask, render_template_string, jsonify
import sqlite3
from datetime import datetime, timezone, timedelta
import threading
import time
import os
import sys
import requests


def get_indian_time():
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = datetime.now(timezone.utc) + ist_offset
    return ist_time.strftime("%Y-%m-%d %H:%M:%S IST")

app = Flask(__name__)

DB_FILE = "trades.db"


def get_current_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=5)
        data = r.json()
        if data and "result" in data:
            return float(data["result"].get("close", 0))
    except:
        pass
    return 0


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_entry TEXT,
        timestamp_exit TEXT,
        symbol TEXT,
        direction TEXT,
        regime TEXT,
        grade TEXT,
        entry_price REAL,
        exit_price REAL,
        size REAL,
        leverage REAL,
        stop_loss REAL,
        take_profit REAL,
        pnl_usd REAL,
        status TEXT,
        signals_fired TEXT,
        htf_aligned INTEGER,
        session TEXT,
        outcome TEXT
    )''')
    conn.commit()
    conn.close()


init_db()


def get_trades(limit=50):
    current_price = get_current_price()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    try:
        if not any(x[1] == 'stop_loss' for x in c.execute("PRAGMA table_info(trades)").fetchall()):
            c.execute("ALTER TABLE trades ADD COLUMN stop_loss REAL DEFAULT 0")
        if not any(x[1] == 'take_profit' for x in c.execute("PRAGMA table_info(trades)").fetchall()):
            c.execute("ALTER TABLE trades ADD COLUMN take_profit REAL DEFAULT 0")
    except:
        pass
    
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    cols = [desc[0] for desc in c.description]
    trades = []
    for row in c.fetchall():
        trade = dict(zip(cols, row))
        
        try:
            trade["entry_price"] = float(trade.get("entry_price", 0) or 0)
            trade["exit_price"] = float(trade.get("exit_price", 0) or 0)
            trade["size"] = float(trade.get("size", 0) or 0)
            trade["leverage"] = float(trade.get("leverage", 1) or 1)
            trade["stop_loss"] = float(trade.get("stop_loss", 0) or 0)
            trade["take_profit"] = float(trade.get("take_profit", 0) or 0)
            
            if trade.get("status") == "open" and current_price > 0:
                leverage = trade["leverage"]
                entry = trade["entry_price"]
                size = trade["size"]
                if trade.get("direction") == "LONG":
                    trade["current_pnl"] = (current_price - entry) * size * leverage
                else:
                    trade["current_pnl"] = (entry - current_price) * size * leverage
                trade["current_price"] = current_price
                trade["invested"] = entry * size
                trade["notional"] = entry * size * leverage
            else:
                trade["current_pnl"] = float(trade.get("pnl_usd", 0))
                trade["current_price"] = trade.get("exit_price", 0)
                trade["invested"] = trade["entry_price"] * trade["size"]
                trade["notional"] = trade["entry_price"] * trade["size"] * trade["leverage"]
        except:
            trade["current_pnl"] = 0
            trade["current_price"] = 0
            trade["invested"] = 0
            trade["notional"] = 0
            
        trades.append(trade)
    conn.close()
    return trades


def get_stats():
    current_price = get_current_price()
    
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
    
    unrealized_pnl = 0
    for trade in open_trades:
        try:
            direction = trade[3]
            entry = float(trade[7])
            size = float(trade[9])
            leverage = float(trade[10] or 1)
            if direction == "LONG":
                pnl = (current_price - entry) * size * leverage
            else:
                pnl = (entry - current_price) * size * leverage
            unrealized_pnl += pnl
        except:
            pass
    
    conn.close()
    
    return {
        "total_pnl": total_pnl or 0,
        "total_trades": total_trades or 0,
        "daily_pnl": daily_pnl or 0,
        "daily_trades": daily_trades or 0,
        "wins": win_count or 0,
        "win_rate": (win_count/total_trades*100) if total_trades and total_trades > 0 else 0,
        "open_positions": len(open_trades),
        "current_price": current_price,
        "unrealized_pnl": unrealized_pnl
    }


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Trading Bot</title>
    <meta http-equiv="refresh" content="15">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); 
            color: #fff; 
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { 
            text-align: center; 
            color: #00ff88; 
            font-size: 2.5rem; 
            margin-bottom: 30px;
            text-shadow: 0 0 20px rgba(0,255,136,0.5);
        }
        .btc-price {
            text-align: center;
            font-size: 1.8rem;
            color: #ffd700;
            margin-bottom: 20px;
        }
        .stats { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 15px; 
            margin-bottom: 30px; 
        }
        .stat-box { 
            background: rgba(255,255,255,0.1); 
            backdrop-filter: blur(10px);
            padding: 20px; 
            border-radius: 15px; 
            border: 1px solid rgba(255,255,255,0.1);
            text-align: center;
            transition: transform 0.3s;
        }
        .stat-box:hover { transform: translateY(-5px); }
        .stat-box h3 { 
            margin: 0 0 10px 0; 
            color: #aaa; 
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .stat-box .value { 
            font-size: 1.8rem; 
            font-weight: bold; 
        }
        .positive { color: #00ff88 !important; }
        .negative { color: #ff4444 !important; }
        
        h2 { 
            color: #00ff88; 
            margin: 30px 0 15px 0;
            font-size: 1.5rem;
            border-bottom: 2px solid #00ff88;
            padding-bottom: 10px;
        }
        
        table { 
            width: 100%; 
            border-collapse: collapse; 
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            overflow: hidden;
        }
        th, td { 
            padding: 12px 15px; 
            text-align: left; 
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { 
            background: rgba(0,255,136,0.2); 
            color: #00ff88;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
        }
        tr:hover { background: rgba(255,255,255,0.05); }
        
        .direction-long { color: #00ff88; font-weight: bold; }
        .direction-short { color: #ff4444; font-weight: bold; }
        
        .pnl-positive { color: #00ff88; }
        .pnl-negative { color: #ff4444; }
        
        .badge {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        .badge-open { background: rgba(0,255,136,0.2); color: #00ff88; }
        .badge-closed { background: rgba(255,255,255,0.2); color: #aaa; }
        
        .last-update { 
            text-align: center; 
            color: #666; 
            font-size: 0.85rem; 
            margin-top: 30px;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .live { animation: pulse 2s infinite; color: #00ff88; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Delta AI Trading Bot</h1>
        
        <div class="btc-price">
            BTC/USD: ${{ "%.2f"|format(stats.current_price) }} <span class="live">● LIVE</span>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <h3>Total PnL</h3>
                <div class="value {{ 'positive' if stats.total_pnl > 0 else 'negative' }}">${{ "%.2f"|format(stats.total_pnl) }}</div>
            </div>
            <div class="stat-box">
                <h3>Unrealized PnL</h3>
                <div class="value {{ 'positive' if stats.unrealized_pnl > 0 else 'negative' }}">${{ "%.2f"|format(stats.unrealized_pnl) }}</div>
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
        
        <h2>📊 Open Positions</h2>
        <table>
            <tr>
                <th>Dir</th>
                <th>Entry</th>
                <th>Current</th>
                <th>Size</th>
                <th>Leverage</th>
                <th>SL</th>
                <th>TP</th>
                <th>Invested</th>
                <th>Notional</th>
                <th>PnL</th>
                <th>Setup</th>
                <th>Time</th>
            </tr>
            {% for trade in trades if trade.status == 'open' %}
            <tr>
                <td class="{{ 'direction-long' if trade.direction == 'LONG' else 'direction-short' }}">{{ trade.direction }}</td>
                <td>${{ "%.2f"|format(trade.entry_price) }}</td>
                <td>${{ "%.2f"|format(trade.current_price) }}</td>
                <td>{{ "%.4f"|format(trade.size) }}</td>
                <td>{{ "%.0f"|format(trade.leverage) }}x</td>
                <td>${{ "%.2f"|format(trade.stop_loss) if trade.stop_loss > 0 else '-' }}</td>
                <td>${{ "%.2f"|format(trade.take_profit) if trade.take_profit > 0 else '-' }}</td>
                <td>${{ "%.2f"|format(trade.invested) }}</td>
                <td>${{ "%.2f"|format(trade.notional) }}</td>
                <td class="{{ 'pnl-positive' if trade.current_pnl > 0 else 'pnl-negative' }}">${{ "%.2f"|format(trade.current_pnl) }}</td>
                <td>{{ trade.grade }}</td>
                <td>{{ trade.timestamp_entry[:19] if trade.timestamp_entry else 'N/A' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="12" style="text-align:center; color:#666;">No open positions</td></tr>
            {% endfor %}
        </table>
        
        <h2>📈 Closed Trades</h2>
        <table>
            <tr>
                <th>Dir</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>Size</th>
                <th>Leverage</th>
                <th>PnL</th>
                <th>Outcome</th>
                <th>Setup</th>
                <th>Time</th>
            </tr>
            {% for trade in trades if trade.status == 'closed' %}
            <tr>
                <td class="{{ 'direction-long' if trade.direction == 'LONG' else 'direction-short' }}">{{ trade.direction }}</td>
                <td>${{ "%.2f"|format(trade.entry_price) }}</td>
                <td>${{ "%.2f"|format(trade.exit_price) }}</td>
                <td>{{ "%.4f"|format(trade.size) }}</td>
                <td>{{ "%.0f"|format(trade.leverage) }}x</td>
                <td class="{{ 'pnl-positive' if trade.pnl_usd > 0 else 'pnl-negative' }}">${{ "%.2f"|format(trade.pnl_usd) }}</td>
                <td>{{ trade.outcome }}</td>
                <td>{{ trade.grade }}</td>
                <td>{{ trade.timestamp_exit[:19] if trade.timestamp_exit else 'N/A' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="9" style="text-align:center; color:#666;">No closed trades</td></tr>
            {% endfor %}
        </table>
        
        <div class="last-update">Last updated: {{ last_update }}</div>
    </div>
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