#!/usr/bin/env python3
"""Web Dashboard - Real-time WebSocket + REST API"""

from flask import Flask, render_template_string, request, redirect
from flask_socketio import SocketIO, emit
import requests
import os
import sys
import time
import threading
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

IST = timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.now(timezone.utc) + IST

def fmt_ist(dt=None):
    dt = dt or now_ist()
    return dt.strftime("%Y-%m-%d %H:%M:%S IST")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
TRADES_FILE = "trades.db"

_last_price = [0]
_price_lock = threading.Lock()

def get_current_price():
    try:
        r = requests.get("https://api.india.delta.exchange/v2/tickers/BTCUSD", timeout=5)
        data = r.json()
        if data and "result" in data:
            price = float(data["result"].get("close", 0))
            with _price_lock:
                _last_price[0] = price
            return price
    except:
        pass
    with _price_lock:
        return _last_price[0]

def get_trade_manager():
    if TradeManager is None:
        return None
    return TradeManager()

def build_trade_dict(trade, current_price=0):
    lev = trade.get("leverage", 1) or 1
    entry = trade.get("entry_price", 0)
    size = trade.get("size", 0)
    side = trade.get("side", "sell")
    status = trade.get("status", "closed")

    d = {
        "id": trade.get("id"),
        "direction": "LONG" if side == "buy" else "SHORT",
        "entry_price": entry,
        "exit_price": trade.get("close_price") or 0,
        "size": size,
        "leverage": lev,
        "stop_loss": trade.get("sl", 0),
        "take_profit": trade.get("tp", 0),
        "pnl_usd": trade.get("pnl") or 0,
        "status": status,
        "signals_fired": trade.get("symbol", ""),
        "timestamp_entry": trade.get("open_time", ""),
        "timestamp_exit": trade.get("close_time", ""),
        "outcome": trade.get("close_reason", "")
    }

    if status == "open" and current_price > 0:
        if side == "buy":
            d["current_pnl"] = (current_price - entry) * size * lev
        else:
            d["current_pnl"] = (entry - current_price) * size * lev
        d["current_price"] = current_price
    else:
        d["current_pnl"] = d["pnl_usd"]
        d["current_price"] = d["exit_price"]

    return d

def get_trades(current_price=None):
    tm = get_trade_manager()
    if tm is None:
        return []
    if current_price is None:
        current_price = get_current_price()
    return [build_trade_dict(t, current_price) for t in tm.get_all_trades()]

def get_closed_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"today": [], "yesterday": [], "history": []}

    closed = tm.get_closed_trades()
    today = now_ist().date()
    yesterday = today - timedelta(days=1)

    today_t, yesterday_t, history_t = [], [], []

    for trade in closed:
        close_time = trade.get("close_time", "")
        if not close_time:
            continue
        try:
            trade_date = datetime.fromisoformat(close_time).date()
        except:
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
            today_t.append(t)
        elif trade_date == yesterday:
            yesterday_t.append(t)
        else:
            history_t.append(t)

    return {"today": today_t, "yesterday": yesterday_t, "history": history_t}

def get_stats(current_price=None):
    tm = get_trade_manager()
    if current_price is None:
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
    total_closed = len(closed_trades)

    today = now_ist().date()
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
        "total_trades": total_closed,
        "daily_pnl": today_pnl,
        "daily_trades": len(today_closed),
        "wins": wins,
        "win_rate": (wins/total_closed*100) if total_closed > 0 else 0,
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

# WebSocket background broadcast thread
_ws_clients = 0

@socketio.on('connect')
def on_connect():
    global _ws_clients
    _ws_clients += 1

@socketio.on('disconnect')
def on_disconnect():
    global _ws_clients
    _ws_clients -= 1

def broadcast_loop():
    while True:
        try:
            if _ws_clients > 0:
                price = get_current_price()
                data = {
                    "stats": get_stats(price),
                    "trades": get_trades(price),
                    "closed": get_closed_trades(),
                    "timestamp": fmt_ist()
                }
                socketio.emit('update', data)
        except:
            pass
        socketio.sleep(2)

def start_broadcaster():
    socketio.start_background_task(broadcast_loop)

start_broadcaster()

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Bot - Live</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: Arial; background: #111; color: #eee; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #0f0; text-align: center; margin-bottom: 15px; }
        .price { text-align: center; font-size: 22px; color: #fa0; margin-bottom: 20px; }
        .price small { font-size: 13px; color: #666; }
        .msg { text-align: center; padding: 10px; margin-bottom: 15px; border-radius: 5px; }
        .msg.green { background: #0a3; color: #fff; }
        .msg.red { background: #a00; color: #fff; }
        .stats { display: flex; gap: 10px; margin-bottom: 25px; flex-wrap: wrap; justify-content: center; }
        .stat { background: #222; padding: 12px 20px; border-radius: 6px; text-align: center; min-width: 120px; }
        .stat h3 { margin: 0 0 5px 0; color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
        .stat .v { font-size: 18px; font-weight: bold; }
        .green { color: #0f0; }
        .red { color: #f44; }
        .flash { animation: flash 0.5s; }
        @keyframes flash { 0% { opacity: 0.3; } 100% { opacity: 1; } }
        h2 { color: #0f0; border-bottom: 1px solid #333; padding: 10px 0; margin: 25px 0 10px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #222; color: #0f0; font-size: 12px; }
        .long { color: #0f0; font-weight: bold; }
        .short { color: #f44; font-weight: bold; }
        .btn { background: #f44; color: #fff; text-decoration: none; padding: 6px 14px; border-radius: 4px; font-size: 12px; cursor: pointer; }
        .btn:hover { background: #f66; }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .empty { text-align: center; color: #666; padding: 20px; }
        .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
        .status-dot.on { background: #0f0; box-shadow: 0 0 6px #0f0; }
        .status-dot.off { background: #f44; }
        #update-time { text-align: center; color: #555; margin-top: 20px; font-size: 12px; }
        .close-result { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Delta Trading Bot</h1>
        <div class="price">
            BTC/USD: $<span id="current-price">{{ "%.2f"|format(stats.current_price) }}</span>
            <span id="price-change"></span>
            <small id="ws-status"><span class="status-dot off"></span>connecting...</small>
        </div>

        <div id="close-msg" class="msg" style="display:none;"></div>

        {% if request.args.get('closed') %}
        <div class="msg green">Position closed! PnL: ${{ request.args.get('pnl') }}</div>
        {% elif request.args.get('error') %}
        <div class="msg red">Error: {{ request.args.get('error') }}</div>
        {% endif %}

        <div class="stats" id="stats-row">
            <div class="stat"><h3>TOTAL PNL</h3><div id="stat-total-pnl" class="v {{ 'green' if stats.total_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.total_pnl) }}</div></div>
            <div class="stat"><h3>UNREALIZED</h3><div id="stat-unrealized" class="v {{ 'green' if stats.unrealized_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.unrealized_pnl) }}</div></div>
            <div class="stat"><h3>DAILY</h3><div id="stat-daily-pnl" class="v {{ 'green' if stats.daily_pnl > 0 else 'red' }}">${{ "%.2f"|format(stats.daily_pnl) }}</div></div>
            <div class="stat"><h3>TRADES</h3><div id="stat-total-trades" class="v">{{ stats.total_trades }}</div></div>
            <div class="stat"><h3>WIN</h3><div id="stat-win-rate" class="v">{{ "%.0f"|format(stats.win_rate) }}%</div></div>
            <div class="stat"><h3>OPEN</h3><div id="stat-open-positions" class="v">{{ stats.open_positions }}</div></div>
        </div>

        <h2>Open Positions</h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Now</th><th>Size</th><th>Lev</th><th>SL</th><th>TP</th><th>PnL</th><th>Action</th></tr>
            <tbody id="open-trades-body">
            {% for t in trades if t.status == 'open' %}
            <tr id="open-{{ t.id }}">
                <td class="{{ 'long' if t.direction == 'LONG' else 'short' }}">{{ t.direction }}</td>
                <td>$<span class="entry-val">{{ "%.0f"|format(t.entry_price) }}</span></td>
                <td>$<span class="now-val">{{ "%.0f"|format(t.current_price) }}</span></td>
                <td class="size-val">{{ "%.4f"|format(t.size) }}</td>
                <td class="lev-val">{{ t.leverage }}x</td>
                <td>${{ "%.0f"|format(t.stop_loss) }}</td>
                <td>${{ "%.0f"|format(t.take_profit) }}</td>
                <td class="pnl-val {{ 'green' if t.current_pnl > 0 else 'red' }}">${{ "%.2f"|format(t.current_pnl) }}</td>
                <td><button onclick="closeTrade('{{ t.id }}')" class="btn" id="close-btn-{{ t.id }}">CLOSE</button></td>
            </tr>
            {% else %}
            <tr id="no-open-trades"><td colspan="9" class="empty">No open positions</td></tr>
            {% endfor %}
            </tbody>
        </table>

        <h2>Today's Closed Trades (<span id="today-count">{{ closed.today|length }}</span>) - PnL: $<span id="today-pnl">{{ "%.2f"|format(stats.today_closed_pnl) }}</span></h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            <tbody id="today-closed-body">
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
            </tbody>
        </table>

        <h2>Yesterday's Closed Trades (<span id="yesterday-count">{{ closed.yesterday|length }}</span>) - PnL: $<span id="yesterday-pnl">{{ "%.2f"|format(stats.yesterday_closed_pnl) }}</span></h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            <tbody id="yesterday-closed-body">
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
            </tbody>
        </table>

        <h2>Historical Closed Trades (<span id="history-count">{{ closed.history|length }}</span>) - PnL: $<span id="history-pnl">{{ "%.2f"|format(stats.history_closed_pnl) }}</span></h2>
        <table>
            <tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr>
            <tbody id="history-closed-body">
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
            </tbody>
        </table>

        <p id="update-time">{{ last_update }}</p>
    </div>

<script>
const socket = io({ transports: ['websocket', 'polling'] });
let lastPrice = {{ stats.current_price }};

socket.on('connect', function() {
    document.getElementById('ws-status').innerHTML = '<span class="status-dot on"></span>live';
});

socket.on('disconnect', function() {
    document.getElementById('ws-status').innerHTML = '<span class="status-dot off"></span>offline';
});

socket.on('update', function(data) {
    const s = data.stats;
    const trades = data.trades;
    const closed = data.closed;

    // Price
    const priceEl = document.getElementById('current-price');
    const oldPrice = parseFloat(priceEl.textContent.replace(',', ''));
    priceEl.textContent = s.current_price.toFixed(2);

    const changeEl = document.getElementById('price-change');
    if (oldPrice > 0) {
        const diff = s.current_price - oldPrice;
        const pct = (diff / oldPrice * 100);
        changeEl.textContent = (diff >= 0 ? '+' : '') + diff.toFixed(2) + ' (' + (diff >= 0 ? '+' : '') + pct.toFixed(2) + '%)';
        changeEl.style.color = diff >= 0 ? '#0f0' : '#f44';
    }
    lastPrice = s.current_price;

    // Stats
    updateStat('stat-total-pnl', '$' + s.total_pnl.toFixed(2), s.total_pnl);
    updateStat('stat-unrealized', '$' + s.unrealized_pnl.toFixed(2), s.unrealized_pnl);
    updateStat('stat-daily-pnl', '$' + s.daily_pnl.toFixed(2), s.daily_pnl);
    updateStat('stat-total-trades', s.total_trades, 0);
    updateStat('stat-win-rate', s.win_rate.toFixed(0) + '%', 0);
    updateStat('stat-open-positions', s.open_positions, 0);

    // Open trades
    const openBody = document.getElementById('open-trades-body');
    const openTrades = trades.filter(function(t) { return t.status === 'open'; });
    if (openTrades.length === 0) {
        openBody.innerHTML = '<tr id="no-open-trades"><td colspan="9" class="empty">No open positions</td></tr>';
    } else {
        let openHtml = '';
        openTrades.forEach(function(t) {
            const dirClass = t.direction === 'LONG' ? 'long' : 'short';
            const pnlClass = t.current_pnl >= 0 ? 'green' : 'red';
            openHtml += '<tr id="open-' + t.id + '">'
                + '<td class="' + dirClass + '">' + t.direction + '</td>'
                + '<td>$<span class="entry-val">' + t.entry_price.toFixed(0) + '</span></td>'
                + '<td>$<span class="now-val">' + t.current_price.toFixed(0) + '</span></td>'
                + '<td class="size-val">' + t.size.toFixed(4) + '</td>'
                + '<td class="lev-val">' + t.leverage + 'x</td>'
                + '<td>$' + (t.stop_loss || 0).toFixed(0) + '</td>'
                + '<td>$' + (t.take_profit || 0).toFixed(0) + '</td>'
                + '<td class="pnl-val ' + pnlClass + '">$' + t.current_pnl.toFixed(2) + '</td>'
                + '<td><button onclick="closeTrade(\'' + t.id + '\')" class="btn" id="close-btn-' + t.id + '">CLOSE</button></td>'
                + '</tr>';
        });
        openBody.innerHTML = openHtml;
    }

    // Closed trades sections
    document.getElementById('today-count').textContent = closed.today.length;
    document.getElementById('today-pnl').textContent = s.today_closed_pnl.toFixed(2);
    document.getElementById('yesterday-count').textContent = closed.yesterday.length;
    document.getElementById('yesterday-pnl').textContent = s.yesterday_closed_pnl.toFixed(2);
    document.getElementById('history-count').textContent = closed.history.length;
    document.getElementById('history-pnl').textContent = s.history_closed_pnl.toFixed(2);

    document.getElementById('today-closed-body').innerHTML = renderClosedRows(closed.today);
    document.getElementById('yesterday-closed-body').innerHTML = renderClosedRows(closed.yesterday);
    document.getElementById('history-closed-body').innerHTML = renderClosedRows(closed.history);

    document.getElementById('update-time').textContent = data.timestamp || s.timestamp || '';
});

function renderClosedRows(trades) {
    if (!trades || trades.length === 0) {
        return '<tr><td colspan="8" class="empty">No trades</td></tr>';
    }
    return trades.map(function(t) {
        const dirClass = t.direction === 'LONG' ? 'long' : 'short';
        const pnlClass = t.pnl_usd >= 0 ? 'green' : 'red';
        return '<tr>'
            + '<td class="' + dirClass + '">' + t.direction + '</td>'
            + '<td>$' + t.entry_price.toFixed(0) + '</td>'
            + '<td>$' + t.exit_price.toFixed(0) + '</td>'
            + '<td>' + t.size.toFixed(4) + '</td>'
            + '<td>' + t.leverage + 'x</td>'
            + '<td class="' + pnlClass + '">$' + t.pnl_usd.toFixed(2) + '</td>'
            + '<td>' + (t.outcome || '') + '</td>'
            + '<td>' + (t.timestamp_exit ? t.timestamp_exit.substring(0, 16) : '') + '</td>'
            + '</tr>';
    }).join('');
}

function updateStat(id, text, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = text;
        el.className = 'v ' + (value >= 0 ? 'green' : 'red');
    }
}

function closeTrade(tradeId) {
    const btn = document.getElementById('close-btn-' + tradeId);
    if (btn) btn.disabled = true;
    fetch('/api/close/' + tradeId)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            const msgEl = document.getElementById('close-msg');
            msgEl.style.display = 'block';
            if (data.success) {
                msgEl.className = 'msg green';
                msgEl.textContent = 'Closed! PnL: $' + data.pnl.toFixed(2);
            } else {
                msgEl.className = 'msg red';
                msgEl.textContent = 'Error: ' + (data.error || 'unknown');
            }
            setTimeout(function() { msgEl.style.display = 'none'; }, 5000);
            if (btn) btn.disabled = false;
        })
        .catch(function() {
            if (btn) btn.disabled = false;
        });
}
</script>
</body>
</html>
"""


@app.route('/')
def index():
    closed = get_closed_trades()
    return render_template_string(HTML, stats=get_stats(), trades=get_trades(), closed=closed, last_update=fmt_ist(), request=request)


@app.route('/close/<trade_id>')
def close_trade_redirect(trade_id):
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
                        result = client.close_position("LONG" if trade["side"] == "buy" else "SHORT", trade["size"])
                        close_success = result is not None
                        break
            except:
                pass

        trade = tm.close_trade(str(trade_id), current_price, "MANUAL_CLOSE" if close_success else "MANUAL_DB_ONLY")
        pnl = trade.get("pnl", 0) if trade else 0
        return redirect('/?closed=1&pnl=' + str(round(pnl, 2)))
    except Exception as e:
        return redirect('/?error=' + str(e))


@app.route('/api/open-trades')
def api_open_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"trades": [], "current_price": get_current_price()}
    return {"trades": [{"id": t.get("id"), "direction": "LONG" if t.get("side") == "buy" else "SHORT",
                        "entry_price": t.get("entry_price", 0), "size": t.get("size", 0),
                        "leverage": t.get("leverage", 1) or 1} for t in tm.get_open_trades()],
            "current_price": get_current_price()}


@app.route('/api/closed-trades')
def api_closed_trades():
    return {"trades": get_closed_trades()}


@app.route('/api/stats')
def api_stats():
    return get_stats()


@app.route('/api/health')
def api_health():
    """Phase 7: Health check endpoint for Render monitoring"""
    tm = get_trade_manager()
    price = get_current_price()
    return {
        "status": "ok",
        "current_price": price,
        "timestamp": fmt_ist(),
        "db_trades_count": len(get_trades()) if tm else 0,
        "db_connected": tm is not None,
        "exchange_api": BOT_AVAILABLE and bool(getattr(config, 'DELTA_API_KEY', '')),
        "mode": "dry_run" if getattr(config, 'DRY_RUN', True) else "live"
    }


@app.route('/api/current-price')
def api_price():
    return {"price": get_current_price(), "timestamp": fmt_ist()}


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
                        result = client.close_position("LONG" if trade["side"] == "buy" else "SHORT", trade["size"])
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
    socketio.run(app, host='0.0.0.0', port=port)
