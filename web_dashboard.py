#!/usr/bin/env python3
"""Web Dashboard - Simple and working"""

from flask import Flask, render_template_string, request, redirect
import sqlite3
from datetime import datetime, timezone, timedelta
import requests
import os

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
        id INTEGER PRIMARY KEY, timestamp_entry TEXT, timestamp_exit TEXT,
        symbol TEXT, direction TEXT, regime TEXT, grade TEXT, entry_price REAL,
        exit_price REAL, size REAL, leverage REAL, stop_loss REAL, take_profit REAL,
        pnl_usd REAL, status TEXT, signals_fired TEXT, htf_aligned INTEGER,
        session TEXT, outcome TEXT
    )''')
    conn.commit()
    conn.close()

init_db()


def get_trades(limit=50):
    current_price = get_current_price()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Add missing columns
    try:
        c.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'closed'")
    except:
        pass
    try:
        c.execute("ALTER TABLE trades ADD COLUMN leverage REAL DEFAULT 1")
    except:
        pass
    try:
        c.execute("ALTER TABLE trades ADD COLUMN stop_loss REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE trades ADD COLUMN take_profit REAL DEFAULT 0")
    except:
        pass
    
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    cols = [desc[0] for desc in c.description]
    trades = []
    for row in c.fetchall():
        trade = dict(zip(cols, row))
        
        try:
            trade["entry_price"] = float(trade.get("entry_price") or 0)
            trade["exit_price"] = float(trade.get("exit_price") or 0)
            trade["size"] = float(trade.get("size") or 0)
            trade["leverage"] = float(trade.get("leverage") or 1)
            trade["stop_loss"] = float(trade.get("stop_loss") or 0)
            trade["take_profit"] = float(trade.get("take_profit") or 0)
            trade["pnl_usd"] = float(trade.get("pnl_usd") or 0)
            trade["status"] = trade.get("status") or "closed"
            
            if trade["status"] == "open" and current_price > 0:
                leverage = trade["leverage"]
                entry = trade["entry_price"]
                size = trade["size"]
                if trade.get("direction") == "LONG":
                    trade["current_pnl"] = (current_price - entry) * size * leverage
                else:
                    trade["current_pnl"] = (entry - current_price) * size * leverage
                trade["current_price"] = current_price
                trade["notional"] = entry * size * leverage
            else:
                trade["current_pnl"] = trade["pnl_usd"]
                trade["current_price"] = trade.get("exit_price") or 0
                trade["notional"] = trade["entry_price"] * trade["size"] * trade["leverage"]
        except Exception as e:
            trade["current_pnl"] = 0
            trade["current_price"] = 0
            trade["notional"] = 0
            trade["status"] = "closed"
        trades.append(trade)
    conn.close()
    return trades


def get_stats():
    current_price = get_current_price()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Ensure status column exists
    try:
        c.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'closed'")
    except:
        pass
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades")
    total_pnl, total_trades = c.fetchone()
    total_trades = total_trades or 0
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now')")
    daily_pnl, daily_trades = c.fetchone()
    daily_trades = daily_trades or 0
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE pnl_usd > 0")
    wins, win_count = c.fetchone()
    
    # Closed trades breakdown - use timestamp_exit
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now')")
    today_closed_pnl, today_closed_count = c.fetchone()
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now', '-1 day')")
    yesterday_closed_pnl, yesterday_closed_count = c.fetchone()
    
    c.execute("SELECT SUM(pnl_usd), COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_exit) < date('now', '-1 day')")
    history_closed_pnl, history_closed_count = c.fetchone()
    
    # Get open trades properly
    c.execute("SELECT direction, entry_price, size, leverage FROM trades WHERE status = 'open'")
    open_trades = c.fetchall()
    
    unrealized_pnl = 0
    for trade in open_trades:
        try:
            direction, entry, size, leverage = trade
            entry = float(entry or 0)
            size = float(size or 0)
            leverage = float(leverage or 1)
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
        "unrealized_pnl": unrealized_pnl,
        "today_closed_pnl": today_closed_pnl or 0,
        "today_closed_count": today_closed_count or 0,
        "yesterday_closed_pnl": yesterday_closed_pnl or 0,
        "yesterday_closed_count": yesterday_closed_count or 0,
        "history_closed_pnl": history_closed_pnl or 0,
        "history_closed_count": history_closed_count or 0
    }


@app.route('/close/<int:trade_id>')
def close_trade(trade_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Get trade details
        c.execute("SELECT direction, entry_price, size, leverage FROM trades WHERE id = ? AND status = 'open'", (trade_id,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return redirect('/?error=not_found')
        
        direction, entry, size, leverage = row
        entry = float(entry or 0)
        size = float(size or 0)
        leverage = float(leverage or 1)
        current_price = get_current_price()
        
        if direction == "LONG":
            pnl = (current_price - entry) * size * leverage
        else:
            pnl = (entry - current_price) * size * leverage
        
        timestamp = datetime.now().isoformat()
        c.execute("""UPDATE trades SET timestamp_exit=?, exit_price=?, pnl_usd=?, status=?, outcome=? 
                    WHERE id=?""", (timestamp, current_price, pnl, "closed", "MANUAL", trade_id))
        conn.commit()
        conn.close()
        
        return redirect('/?closed=1&pnl=' + str(round(pnl, 2)))
    except Exception as e:
        return redirect('/?error=' + str(e))


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Trading Bot</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body { font-family: Arial; background: #111; color: #eee; margin: 0; padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; }
        h1 { color: #0f0; text-align: center; margin-bottom: 15px; }
        .price { text-align: center; font-size: 22px; color: #fa0; margin-bottom: 20px; }
        .msg { text-align: center; padding: 10px; margin-bottom: 15px; border-radius: 5px; }
        .msg.green { background: #0a3; color: #fff; }
        .msg.red { background: #a00; color: #fff; }
        .stats { display: flex; gap: 10px; margin-bottom: 25px; flex-wrap: wrap; justify-content: center; }
        .stat { background: #222; padding: 12px 20px; border-radius: 6px; text-align: center; min-width: 120px; }
        .stat h3 { margin: 0 0 5px 0; color: #888; font-size: 11px; }
        .stat .v { font-size: 18px; font-weight: bold; }
        .green { color: #0f0; }
        .red { color: #f44; }
        h2 { color: #0f0; border-bottom: 1px solid #333; padding: 10px 0; margin: 25px 0 10px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #222; color: #0f0; font-size: 12px; }
        .long { color: #0f0; font-weight: bold; }
        .short { color: #f44; font-weight: bold; }
        .btn { background: #f44; color: #fff; text-decoration: none; padding: 6px 14px; 
               border-radius: 4px; font-size: 12px; }
        .btn:hover { background: #f66; }
        .empty { text-align: center; color: #666; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Delta Trading Bot</h1>
        <div class="price">BTC/USD: ${{ "%.2f"|format(stats.current_price) }}</div>
        
        {% if request.args.get('closed') %}
        <div class="msg green">Position closed! PnL: ${{ request.args.get('pnl') }}</div>
        {% elif request.args.get('error') %}
        <div class="msg red">Error: {{ request.args.get('error') }}</div>
        {% endif %}
        
        <div class="stats">
            <div class="stat"><h3>TOTAL PNL</h3><div class="v {{ 'green' if stats.total_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.total_pnl) }}</div></div>
            <div class="stat"><h3>UNREALIZED</h3><div class="v {{ 'green' if stats.unrealized_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.unrealized_pnl) }}</div></div>
            <div class="stat"><h3>DAILY</h3><div class="v {{ 'green' if stats.daily_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.daily_pnl) }}</div></div>
            <div class="stat"><h3>TRADES</h3><div class="v">{{ stats.total_trades }}</div></div>
            <div class="stat"><h3>WIN</h3><div class="v">{{ "%.0f"|format(stats.win_rate) }}%</div></div>
            <div class="stat"><h3>OPEN</h3><div class="v">{{ stats.open_positions }}</div></div>
        </div>
        
        <h2>Open Positions</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Now</th><th>Size</th><th>Lev</th><th>SL</th><th>TP</th><th>PnL</th><th>Setup</th><th>Close</th></tr>
            {% for t in trades if t.status == 'open' %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.current_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td>{{ "%.0f"|format(t.leverage) }}x</td>
                <td>${{ "%.0f"|format(t.stop_loss) }}</td>
                <td>${{ "%.0f"|format(t.take_profit) }}</td>
                <td class="{{ 'green' if t.current_pnl > 0 else 'red' }}">${{ "%.2f"|format(t.current_pnl) }}</td>
                <td>{{ t.grade }}</td>
                <td><a href="/close/{{ t.id }}" class="btn">CLOSE</a></td>
            </tr>
            {% else %}
            <tr><td colspan="10" class="empty">No open positions</td></tr>
            {% endfor %}
        </table>
        
        <h2>Today's Closed Trades ({{ closed.today|length }}) - PnL: ${{ "%.2f"|format(stats.today_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>PnL</th><th>Result</th><th>Setup</th><th>Time</th></tr>
            {% for t in closed.today %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.grade }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No trades today</td></tr>
            {% endfor %}
        </table>
        
        <h2>Yesterday's Closed Trades ({{ closed.yesterday|length }}) - PnL: ${{ "%.2f"|format(stats.yesterday_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>PnL</th><th>Result</th><th>Setup</th><th>Time</th></tr>
            {% for t in closed.yesterday %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.grade }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No trades yesterday</td></tr>
            {% endfor %}
        </table>
        
        <h2>Historical Closed Trades ({{ closed.history|length }}) - PnL: ${{ "%.2f"|format(stats.history_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>PnL</th><th>Result</th><th>Setup</th><th>Time</th></tr>
            {% for t in closed.history %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.grade }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No historical trades</td></tr>
            {% endfor %}
        </table>
        
        <h2>All Closed Trades - Total PnL: ${{ "%.2f"|format(stats.today_closed_pnl + stats.yesterday_closed_pnl + stats.history_closed_pnl) }}</h2>
        
        <p style="text-align:center; color:#555; margin-top:20px;">{{ last_update }}</p>
    </div>
</body>
</html>
"""


def get_closed_trades():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Today's closed trades (by exit time, not entry)
    c.execute("SELECT * FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now') ORDER BY id DESC")
    today_cols = [desc[0] for desc in c.description]
    today_trades = [dict(zip(today_cols, row)) for row in c.fetchall()]
    
    # Yesterday's closed trades
    c.execute("SELECT * FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now', '-1 day') ORDER BY id DESC")
    yesterday_cols = [desc[0] for desc in c.description]
    yesterday_trades = [dict(zip(yesterday_cols, row)) for row in c.fetchall()]
    
    # History closed trades
    c.execute("SELECT * FROM trades WHERE status = 'closed' AND date(timestamp_exit) < date('now', '-1 day') ORDER BY id DESC")
    history_cols = [desc[0] for desc in c.description]
    history_trades = [dict(zip(history_cols, row)) for row in c.fetchall()]
    
    conn.close()
    
    return {
        "today": today_trades,
        "yesterday": yesterday_trades,
        "history": history_trades
    }


# ===== API ENDPOINTS FOR REAL-TIME DATA =====
@app.route('/api/open-trades')
def api_open_trades():
    """Return all open trades with live PnL"""
    current_price = get_current_price()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""SELECT id, direction, entry_price, size, leverage, stop_loss, take_profit, 
                 signals_fired, timestamp_entry FROM trades WHERE status = 'open'""")
    
    trades = []
    for row in c.fetchall():
        trade_id, direction, entry, size, lev, sl, tp, setup, timestamp = row
        entry = float(entry or 0)
        size = float(size or 0)
        lev = float(lev or 1)
        
        # Calculate live PnL
        if direction == "LONG":
            pnl = (current_price - entry) * size * lev
        else:
            pnl = (entry - current_price) * size * lev
        
        trades.append({
            "id": trade_id,
            "direction": direction,
            "entry_price": entry,
            "current_price": current_price,
            "size": size,
            "leverage": lev,
            "stop_loss": float(sl or 0),
            "take_profit": float(tp or 0),
            "pnl": round(pnl, 2),
            "setup": setup,
            "timestamp": timestamp
        })
    
    conn.close()
    return {"trades": trades, "current_price": current_price}


@app.route('/api/closed-trades')
def api_closed_trades():
    """Return all closed trades"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""SELECT id, direction, entry_price, exit_price, size, leverage, pnl_usd, 
                 signals_fired, outcome, timestamp_entry, timestamp_exit 
                 FROM trades WHERE status = 'closed' ORDER BY id DESC""")
    
    trades = []
    for row in c.fetchall():
        trades.append({
            "id": row[0],
            "direction": row[1],
            "entry_price": float(row[2] or 0),
            "exit_price": float(row[3] or 0),
            "size": float(row[4] or 0),
            "leverage": float(row[5] or 1),
            "pnl": float(row[6] or 0),
            "setup": row[7],
            "outcome": row[8],
            "timestamp_entry": row[9],
            "timestamp_exit": row[10]
        })
    
    conn.close()
    return {"trades": trades}


@app.route('/api/stats')
def api_stats():
    """Return stats as JSON"""
    return get_stats()


@app.route('/api/current-price')
def api_price():
    """Return current price"""
    price = get_current_price()
    return {"price": price, "timestamp": get_indian_time()}


@app.route('/api/close/<int:trade_id>')
def api_close_trade(trade_id):
    """Close a trade via API"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("SELECT direction, entry_price, size, leverage FROM trades WHERE id = ? AND status = 'open'", (trade_id,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return {"success": False, "error": "Trade not found"}
        
        direction, entry, size, leverage = row
        entry = float(entry or 0)
        size = float(size or 0)
        leverage = float(leverage or 1)
        current_price = get_current_price()
        
        if direction == "LONG":
            pnl = (current_price - entry) * size * leverage
        else:
            pnl = (entry - current_price) * size * leverage
        
        timestamp = datetime.now().isoformat()
        c.execute("""UPDATE trades SET timestamp_exit=?, exit_price=?, pnl_usd=?, status=?, outcome=? 
                    WHERE id=?""", (timestamp, current_price, pnl, "closed", "MANUAL", trade_id))
        conn.commit()
        conn.close()
        
        return {"success": True, "pnl": round(pnl, 2), "exit_price": current_price}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route('/')
def index():
    closed = get_closed_trades()
    return render_template_string(HTML, stats=get_stats(), trades=get_trades(), closed=closed, last_update=get_indian_time(), request=request)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)