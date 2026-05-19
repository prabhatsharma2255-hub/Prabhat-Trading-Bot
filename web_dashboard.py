#!/usr/bin/env python3
"""Web Dashboard - Reads from trades.db"""

from flask import Flask, render_template_string, request, redirect
import requests
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from trade_manager import TradeManager
except:
    TradeManager = None

try:
    import config
    from delta_client import DeltaClient
    BOT_AVAILABLE = True
except:
    BOT_AVAILABLE = False

def get_indian_time():
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = datetime.now(timezone.utc) + ist_offset
    return ist_time.strftime("%Y-%m-%d %H:%M:%S IST")

app = Flask(__name__)
TRADES_FILE = "trades.db"

def get_current_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=5)
        data = r.json()
        if data and "result" in data:
            return float(data["result"].get("close", 0))
    except:
        pass
    return 0

def get_trade_manager():
    if TradeManager is None:
        return None
    return TradeManager()

def get_trades():
    tm = get_trade_manager()
    if tm is None:
        return []

    current_price = get_current_price()
    trades = []

    for trade in tm.get_all_trades():
        lev = trade.get("leverage", 1) or 1
        t = {
            "id": trade.get("id"),
            "direction": "LONG" if trade.get("side") == "buy" else "SHORT",
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("close_price") or 0,
            "size": trade.get("size", 0),
            "leverage": lev,
            "stop_loss": trade.get("sl", 0),
            "take_profit": trade.get("tp", 0),
            "pnl_usd": trade.get("pnl") or 0,
            "status": trade.get("status", "closed"),
            "signals_fired": trade.get("symbol", ""),
            "timestamp_entry": trade.get("open_time", ""),
            "timestamp_exit": trade.get("close_time", ""),
            "outcome": trade.get("close_reason", "")
        }

        if t["status"] == "open" and current_price > 0:
            entry = t["entry_price"]
            size = t["size"]
            if t["direction"] == "LONG":
                t["current_pnl"] = (current_price - entry) * size * lev
            else:
                t["current_pnl"] = (entry - current_price) * size * lev
            t["current_price"] = current_price
        else:
            t["current_pnl"] = t["pnl_usd"]
            t["current_price"] = t["exit_price"]

        trades.append(t)

    return trades

def get_closed_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"today": [], "yesterday": [], "history": []}

    closed = tm.get_closed_trades()

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    today_trades = []
    yesterday_trades = []
    history_trades = []

    for trade in closed:
        close_time = trade.get("close_time", "")
        if close_time:
            try:
                trade_date = datetime.fromisoformat(close_time).date()
            except:
                trade_date = today
        else:
            continue

        lev = trade.get("leverage", 1) or 1
        t = {
            "id": trade.get("id"),
            "direction": "LONG" if trade.get("side") == "buy" else "SHORT",
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("close_price") or 0,
            "size": trade.get("size", 0),
            "leverage": lev,
            "pnl_usd": trade.get("pnl") or 0,
            "signals_fired": trade.get("symbol", ""),
            "outcome": trade.get("close_reason", ""),
            "timestamp_exit": close_time
        }

        if trade_date == today:
            today_trades.append(t)
        elif trade_date == yesterday:
            yesterday_trades.append(t)
        else:
            history_trades.append(t)

    return {
        "today": today_trades,
        "yesterday": yesterday_trades,
        "history": history_trades
    }

def get_stats():
    tm = get_trade_manager()
    current_price = get_current_price()

    if tm is None:
        return {
            "total_pnl": 0, "total_trades": 0, "daily_pnl": 0, "daily_trades": 0,
            "wins": 0, "win_rate": 0, "open_positions": 0, "current_price": current_price,
            "unrealized_pnl": 0, "today_closed_pnl": 0, "today_closed_count": 0,
            "yesterday_closed_pnl": 0, "yesterday_closed_count": 0,
            "history_closed_pnl": 0, "history_closed_count": 0
        }

    open_trades = tm.get_open_trades()
    closed_trades = tm.get_closed_trades()

    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl") or 0) > 0)
    total_trades = len(closed_trades)

    today = datetime.now().date()
    today_closed = [t for t in closed_trades if t.get("close_time") and
                   datetime.fromisoformat(t["close_time"]).date() == today]
    today_pnl = sum(t.get("pnl", 0) or 0 for t in today_closed)

    unrealized = 0
    for trade in open_trades:
        lev = trade.get("leverage", 1) or 1
        size = trade.get("size", 0) or 0
        entry = trade.get("entry_price", 0)
        if trade.get("side") == "buy":
            unrealized += (current_price - entry) * size * lev
        else:
            unrealized += (entry - current_price) * size * lev

    yesterday = today - timedelta(days=1)
    yesterday_closed = [t for t in closed_trades if t.get("close_time") and
                      datetime.fromisoformat(t["close_time"]).date() == yesterday]
    yesterday_pnl = sum(t.get("pnl", 0) or 0 for t in yesterday_closed)

    history_closed = [t for t in closed_trades if t.get("close_time") and
                     datetime.fromisoformat(t["close_time"]).date() < yesterday]
    history_pnl = sum(t.get("pnl", 0) or 0 for t in history_closed)

    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "daily_pnl": today_pnl,
        "daily_trades": len(today_closed),
        "wins": wins,
        "win_rate": (wins/total_trades*100) if total_trades > 0 else 0,
        "open_positions": len(open_trades),
        "current_price": current_price,
        "unrealized_pnl": unrealized,
        "today_closed_pnl": today_pnl,
        "today_closed_count": len(today_closed),
        "yesterday_closed_pnl": yesterday_pnl,
        "yesterday_closed_count": len(yesterday_closed),
        "history_closed_pnl": history_pnl,
        "history_closed_count": len(history_closed)
    }


@app.route('/close/<trade_id>')
def close_trade(trade_id):
    tm = get_trade_manager()
    if tm is None:
        return redirect('/?error=trade_manager_not_available')

    try:
        current_price = get_current_price()

        close_success = False
        if BOT_AVAILABLE and hasattr(config, 'DELTA_API_KEY') and config.DELTA_API_KEY:
            try:
                client = DeltaClient(config.DELTA_API_KEY, config.DELTA_API_SECRET)
                for trade in tm.get_open_trades():
                    if str(trade["id"]) == str(trade_id):
                        side = trade["side"]
                        size = trade["size"]
                        result = client.close_position("LONG" if side == "buy" else "SHORT", size)
                        close_success = result is not None
                        break
            except Exception as e:
                print(f"Exchange close error: {e}")

        trade = tm.close_trade(str(trade_id), current_price, "MANUAL_CLOSE" if close_success else "MANUAL_DB_ONLY")

        if trade:
            pnl = trade.get("pnl", 0)
        else:
            pnl = 0

        return redirect('/?closed=1&pnl=' + str(round(pnl, 2)))
    except Exception as e:
        return redirect('/?error=' + str(e))


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Trading Bot</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: Arial; background: #111; color: #eee; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
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
        .btn { background: #f44; color: #fff; text-decoration: none; padding: 6px 14px; border-radius: 4px; font-size: 12px; }
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
            <tr><th>Dir</th><th>Entry</th><th>Now</th><th>Size</th><th>Lev</th><th>SL</th><th>TP</th><th>PnL</th><th>Close</th></tr>
            {% for t in trades if t.status == 'open' %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.current_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td>{{ t.leverage }}x</td>
                <td>${{ "%.0f"|format(t.stop_loss) }}</td>
                <td>${{ "%.0f"|format(t.take_profit) }}</td>
                <td class="{{ 'green' if t.current_pnl > 0 else 'red' }}">${{ "%.2f"|format(t.current_pnl) }}</td>
                <td><a href="/close/{{ t.id }}" class="btn">CLOSE</a></td>
            </tr>
            {% else %}
            <tr><td colspan="9" class="empty">No open positions</td></tr>
            {% endfor %}
        </table>

        <h2>Today's Closed Trades ({{ closed.today|length }}) - PnL: ${{ "%.2f"|format(stats.today_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            {% for t in closed.today %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td>{{ t.leverage }}x</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No trades today</td></tr>
            {% endfor %}
        </table>

        <h2>Yesterday's Closed Trades ({{ closed.yesterday|length }}) - PnL: ${{ "%.2f"|format(stats.yesterday_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            {% for t in closed.yesterday %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td>{{ t.leverage }}x</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No trades yesterday</td></tr>
            {% endfor %}
        </table>

        <h2>Historical Closed Trades ({{ closed.history|length }}) - PnL: ${{ "%.2f"|format(stats.history_closed_pnl) }}</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            {% for t in closed.history %}
            <tr>
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>${{ "%.0f"|format(t.entry_price) }}</td>
                <td>${{ "%.0f"|format(t.exit_price) }}</td>
                <td>{{ "%.4f"|format(t.size) }}</td>
                <td>{{ t.leverage }}x</td>
                <td class="{{ 'green' if t.pnl_usd > 0 else 'red' }}">${{ "%.2f"|format(t.pnl_usd) }}</td>
                <td>{{ t.outcome }}</td>
                <td>{{ t.timestamp_exit[:16] if t.timestamp_exit else '' }}</td>
            </tr>
            {% else %}
            <tr><td colspan="8" class="empty">No historical trades</td></tr>
            {% endfor %}
        </table>

        <p style="text-align:center; color:#555; margin-top:20px;">{{ last_update }}</p>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    closed = get_closed_trades()
    return render_template_string(HTML, stats=get_stats(), trades=get_trades(), closed=closed, last_update=get_indian_time(), request=request)


@app.route('/api/open-trades')
def api_open_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"trades": [], "current_price": get_current_price()}

    current_price = get_current_price()
    trades = []

    for trade in tm.get_open_trades():
        entry = trade.get("entry_price", 0)
        size = trade.get("size", 0)
        lev = trade.get("leverage", 1) or 1

        if trade.get("side") == "buy":
            pnl = (current_price - entry) * size * lev
        else:
            pnl = (entry - current_price) * size * lev

        trades.append({
            "id": trade.get("id"),
            "direction": "LONG" if trade.get("side") == "buy" else "SHORT",
            "entry_price": entry,
            "current_price": current_price,
            "size": size,
            "leverage": lev,
            "pnl": round(pnl, 2)
        })

    return {"trades": trades, "current_price": current_price}


@app.route('/api/closed-trades')
def api_closed_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"trades": []}

    trades = []
    for trade in tm.get_closed_trades():
        lev = trade.get("leverage", 1) or 1
        trades.append({
            "id": trade.get("id"),
            "direction": "LONG" if trade.get("side") == "buy" else "SHORT",
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("close_price") or 0,
            "size": trade.get("size", 0),
            "leverage": lev,
            "pnl": trade.get("pnl") or 0,
            "timestamp_entry": trade.get("open_time", ""),
            "timestamp_exit": trade.get("close_time", "")
        })

    return {"trades": trades}


@app.route('/api/stats')
def api_stats():
    return get_stats()


@app.route('/api/current-price')
def api_price():
    return {"price": get_current_price(), "timestamp": get_indian_time()}


@app.route('/api/close/<trade_id>')
def api_close_trade(trade_id):
    tm = get_trade_manager()
    if tm is None:
        return {"success": False, "error": "TradeManager not available"}

    try:
        current_price = get_current_price()

        close_success = False
        if BOT_AVAILABLE and hasattr(config, 'DELTA_API_KEY') and config.DELTA_API_KEY:
            try:
                client = DeltaClient(config.DELTA_API_KEY, config.DELTA_API_SECRET)
                for trade in tm.get_open_trades():
                    if str(trade["id"]) == str(trade_id):
                        side = trade["side"]
                        size = trade["size"]
                        result = client.close_position("LONG" if side == "buy" else "SHORT", size)
                        close_success = result is not None
                        break
            except:
                pass

        trade = tm.close_trade(str(trade_id), current_price, "MANUAL_CLOSE" if close_success else "MANUAL_DB_ONLY")

        pnl = trade.get("pnl", 0) if trade else 0

        return {"success": True, "pnl": round(pnl, 2), "exit_price": current_price, "exchange_closed": close_success}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
