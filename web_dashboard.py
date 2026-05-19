#!/usr/bin/env python3
"""Web Dashboard - Real-time WebSocket + REST API"""

from flask import Flask, render_template_string, request, redirect, jsonify
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

def get_closed_trades():
    tm = get_trade_manager()
    if tm is None:
        return {"today": [], "yesterday": [], "history": []}
    closed = tm.get_closed_trades()
    today = now_ist().date()
    yesterday = today - timedelta(days=1)
    today_t, yesterday_t, history_t = [], [], []
    for trade in closed:
        ct = trade.get("close_time", "")
        if not ct:
            continue
        try:
            td = datetime.fromisoformat(ct).date()
        except:
            continue
        lev = trade.get("leverage", 1) or 1
        t = {"id": trade.get("id"), "direction": "LONG" if trade.get("side") == "buy" else "SHORT",
             "entry_price": trade.get("entry_price", 0), "exit_price": trade.get("close_price") or 0,
             "size": trade.get("size", 0), "leverage": lev, "pnl_usd": trade.get("pnl") or 0,
             "result": trade.get("close_reason", ""), "time": ct}
        if td == today:
            today_t.append(t)
        elif td == yesterday:
            yesterday_t.append(t)
        else:
            history_t.append(t)
    return {"today": today_t, "yesterday": yesterday_t, "history": history_t}

def get_all_data():
    price = get_current_price()
    tm = get_trade_manager()
    if tm is None:
        return {"price": price, "stats": {"total_pnl": 0, "daily_pnl": 0, "total_trades": 0, "wins": 0, "win_rate": 0, "open_positions": 0, "unrealized_pnl": 0},
                "open": [], "closed": get_closed_trades(), "timestamp": fmt_ist()}

    open_trades = tm.get_open_trades()
    closed_trades = tm.get_closed_trades()

    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl") or 0) > 0)
    total_closed = len(closed_trades)
    win_rate = (wins/total_closed*100) if total_closed > 0 else 0

    today = now_ist().date()
    today_closed = [t for t in closed_trades if t.get("close_time") and
                   datetime.fromisoformat(t["close_time"]).date() == today]
    daily_pnl = sum(t.get("pnl", 0) or 0 for t in today_closed)

    unrealized = 0
    for t in open_trades:
        lev = t.get("leverage", 1) or 1
        sz = t.get("size", 0) or 0
        entry = t.get("entry_price", 0)
        if t.get("side") == "buy":
            unrealized += (price - entry) * sz * lev
        else:
            unrealized += (entry - price) * sz * lev

    open_list = []
    for t in open_trades:
        lev = t.get("leverage", 1) or 1
        sz = t.get("size", 0) or 0
        entry = t.get("entry_price", 0)
        side = t.get("side", "sell")
        if side == "buy":
            pnl = (price - entry) * sz * lev
        else:
            pnl = (entry - price) * sz * lev
        open_list.append({
            "id": t.get("id"), "direction": "LONG" if side == "buy" else "SHORT",
            "entry": entry, "size": sz, "leverage": lev,
            "sl": t.get("sl", 0), "tp": t.get("tp", 0), "pnl": round(pnl, 2)
        })

    return {
        "price": price,
        "stats": {"total_pnl": round(total_pnl, 2), "daily_pnl": round(daily_pnl, 2),
                  "total_trades": total_closed, "wins": wins, "win_rate": round(win_rate, 1),
                  "open_positions": len(open_trades), "unrealized_pnl": round(unrealized, 2)},
        "open": open_list,
        "closed": get_closed_trades(),
        "timestamp": fmt_ist()
    }

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Delta Trading Bot</title>
    <meta charset="utf-8">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial; background: #0a0a0f; color: #ddd; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #0c6; text-align: center; font-size: 20px; margin-bottom: 12px; letter-spacing: 1px; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 8px; }
        .price-box { font-size: 22px; color: #fa0; font-weight: bold; }
        .price-box small { font-size: 12px; color: #666; font-weight: normal; }
        .status-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; padding: 4px 10px; border-radius: 12px; background: #222; }
        .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .dot.green { background: #0c6; box-shadow: 0 0 6px #0c6; }
        .dot.red { background: #f44; }
        .dot.yellow { background: #fa0; }
        .change { font-size: 13px; font-weight: normal; margin-left: 8px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin-bottom: 20px; }
        .stat { background: #151520; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #222; }
        .stat label { display: block; font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
        .stat .val { font-size: 18px; font-weight: bold; }
        .green { color: #0c6; }
        .red { color: #f44; }
        .section-title { color: #0c6; font-size: 14px; border-bottom: 1px solid #222; padding: 12px 0 6px 0; margin: 18px 0 8px 0; display: flex; justify-content: space-between; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #151520; color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; padding: 8px 6px; text-align: left; border-bottom: 1px solid #222; }
        td { padding: 8px 6px; border-bottom: 1px solid #151520; }
        .long { color: #0c6; }
        .short { color: #f44; }
        .btn { background: #f44; color: #fff; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 11px; }
        .btn:hover { opacity: 0.8; }
        .btn:disabled { opacity: 0.3; cursor: default; }
        .empty { text-align: center; color: #444; padding: 16px; }
        .msg { padding: 10px 16px; border-radius: 6px; margin-bottom: 12px; text-align: center; font-size: 13px; display: none; }
        .msg.green { background: #0c622; color: #0c6; display: block; }
        .msg.red { background: #442; color: #f44; display: block; }
        #footer { text-align: center; color: #333; font-size: 11px; margin-top: 20px; }
        .tab-bar { display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap; }
        .tab { background: #151520; color: #888; border: 1px solid #222; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .tab.active { background: #0c6; color: #000; border-color: #0c6; font-weight: bold; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .stats { grid-template-columns: repeat(3, 1fr); }
            .stat { padding: 8px; }
            .stat .val { font-size: 14px; }
            table { font-size: 11px; }
            th, td { padding: 5px 3px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>DELTA TRADING BOT</h1>

    <div class="top-bar">
        <div class="price-box">BTC/USD: $<span id="price">--</span><span class="change" id="change"></span></div>
        <span class="status-badge"><span class="dot yellow" id="status-dot"></span><span id="status-text">loading...</span></span>
    </div>

    <div id="msg" class="msg"></div>

    <div class="stats" id="stats">
        <div class="stat"><label>Total PnL</label><div class="val" id="s-total">--</div></div>
        <div class="stat"><label>Unrealized</label><div class="val" id="s-unreal">--</div></div>
        <div class="stat"><label>Daily PnL</label><div class="val" id="s-daily">--</div></div>
        <div class="stat"><label>Trades</label><div class="val" id="s-trades">--</div></div>
        <div class="stat"><label>Win Rate</label><div class="val" id="s-winrate">--</div></div>
        <div class="stat"><label>Open</label><div class="val" id="s-open">--</div></div>
    </div>

    <div class="section-title">Open Positions <span id="open-count" style="color:#888;font-weight:normal;"></span></div>
    <table><thead><tr><th>Dir</th><th>Entry</th><th>Size</th><th>Lev</th><th>SL</th><th>TP</th><th>PnL</th><th></th></tr></thead><tbody id="open-body"></tbody></table>

    <div class="tab-bar">
        <div class="tab active" onclick="switchTab('today')">Today</div>
        <div class="tab" onclick="switchTab('yesterday')">Yesterday</div>
        <div class="tab" onclick="switchTab('all')">All Closed</div>
    </div>

    <div id="tab-today" class="tab-content active">
        <div class="section-title">Today's Closed Trades <span id="today-info" style="color:#888;font-weight:normal;"></span></div>
        <table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id="today-body"></tbody></table>
    </div>

    <div id="tab-yesterday" class="tab-content">
        <div class="section-title">Yesterday <span id="yesterday-info" style="color:#888;font-weight:normal;"></span></div>
        <table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id="yesterday-body"></tbody></table>
    </div>

    <div id="tab-all" class="tab-content">
        <div class="section-title">All Closed Trades <span id="all-info" style="color:#888;font-weight:normal;"></span></div>
        <table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id="all-body"></tbody></table>
    </div>

    <div id="footer"></div>
</div>

<script>
let lastPrice = 0;
let retryCount = 0;

function fetchData() {
    fetch('/api/all')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            try {
                retryCount = 0;
                document.getElementById('status-dot').className = 'dot green';
                document.getElementById('status-text').textContent = 'live';

                var s = d.stats || {};
                var price = typeof d.price === 'number' ? d.price : 0;

                // Price
                var priceEl = document.getElementById('price');
                var oldP = lastPrice || price;
                priceEl.textContent = price.toFixed(2);
                var diff = price - oldP;
                var changeEl = document.getElementById('change');
                if (diff !== 0 && lastPrice > 0) {
                    changeEl.textContent = (diff > 0 ? '+' : '') + diff.toFixed(2) + ' (' + (diff > 0 ? '+' : '') + (diff/oldP*100).toFixed(2) + '%)';
                    changeEl.style.color = diff > 0 ? '#0c6' : '#f44';
                } else {
                    changeEl.textContent = '';
                }
                lastPrice = price;

                // Stats
                setStat('s-total', '$' + (s.total_pnl || 0).toFixed(2), s.total_pnl || 0);
                setStat('s-unreal', '$' + (s.unrealized_pnl || 0).toFixed(2), s.unrealized_pnl || 0);
                setStat('s-daily', '$' + (s.daily_pnl || 0).toFixed(2), s.daily_pnl || 0);
                document.getElementById('s-trades').textContent = s.total_trades || 0;
                document.getElementById('s-winrate').textContent = (s.win_rate || 0) + '%';
                document.getElementById('s-open').textContent = s.open_positions || 0;

                // Open positions
                var openList = d.open || [];
                var openBody = document.getElementById('open-body');
                document.getElementById('open-count').textContent = '(' + openList.length + ')';
                if (openList.length === 0) {
                    openBody.innerHTML = '<tr><td colspan="8" class="empty">No open positions</td></tr>';
                } else {
                    openBody.innerHTML = openList.map(function(t) {
                        var cls = t.direction === 'LONG' ? 'long' : 'short';
                        var pnlCls = t.pnl >= 0 ? 'green' : 'red';
                        return '<tr><td class="' + cls + '">' + (t.direction || '') + '</td>'
                            + '<td>$' + (t.entry || 0).toFixed(0) + '</td>'
                            + '<td>' + (t.size || 0).toFixed(4) + '</td>'
                            + '<td>' + (t.leverage || 0) + 'x</td>'
                            + '<td>$' + (t.sl || 0).toFixed(0) + '</td>'
                            + '<td>$' + (t.tp || 0).toFixed(0) + '</td>'
                            + '<td class="' + pnlCls + '">$' + (t.pnl || 0).toFixed(2) + '</td>'
                            + '<td><button onclick="closeTrade(\'' + (t.id || '') + '\')" class="btn">X</button></td></tr>';
                    }).join('');
                }

                // Closed trades
                var c = d.closed || {};
                var todayList = c.today || [];
                var yesterdayList = c.yesterday || [];
                var allList = [].concat(todayList, c.yesterday || [], c.history || []);
                document.getElementById('today-info').textContent = todayList.length + ' trades | PnL: $' + (s.daily_pnl || 0).toFixed(2);
                document.getElementById('today-body').innerHTML = renderClosed(todayList);
                document.getElementById('yesterday-info').textContent = yesterdayList.length + ' trades';
                document.getElementById('yesterday-body').innerHTML = renderClosed(yesterdayList);
                document.getElementById('all-info').textContent = allList.length + ' trades total';
                document.getElementById('all-body').innerHTML = renderClosed(allList);

                document.getElementById('footer').textContent = d.timestamp || '';
            } catch(e) {
                console.error('Dashboard render error:', e);
            }
        })
        .catch(function() {
            retryCount++;
            var dotEl = document.getElementById('status-dot');
            var textEl = document.getElementById('status-text');
            if (dotEl && textEl) {
                dotEl.className = 'dot ' + (retryCount > 5 ? 'red' : 'yellow');
                textEl.textContent = retryCount > 5 ? 'offline' : 'retrying...';
            }
        });
}

function setStat(id, text, val) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'val ' + (val >= 0 ? 'green' : 'red');
}

function renderClosed(trades) {
    if (!trades || trades.length === 0) return '<tr><td colspan="8" class="empty">No trades</td></tr>';
    return trades.map(function(t) {
        var cls = t.direction === 'LONG' ? 'long' : 'short';
        var pnlVal = t.pnl_usd || 0;
        var pnlCls = pnlVal >= 0 ? 'green' : 'red';
        return '<tr><td class="' + cls + '">' + (t.direction || '') + '</td>'
            + '<td>$' + (t.entry_price || 0).toFixed(0) + '</td>'
            + '<td>$' + (t.exit_price || 0).toFixed(0) + '</td>'
            + '<td>' + (t.size || 0).toFixed(4) + '</td>'
            + '<td>' + (t.leverage || 0) + 'x</td>'
            + '<td class="' + pnlCls + '">$' + pnlVal.toFixed(2) + '</td>'
            + '<td>' + (t.result || '') + '</td>'
            + '<td>' + (t.time ? t.time.substring(0, 16) : '') + '</td></tr>';
    }).join('');
}

function closeTrade(id) {
    if (!id) return;
    var btn = document.querySelector('button[onclick*="' + id + '"]');
    if (btn) btn.disabled = true;
    fetch('/api/close/' + id)
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var msg = document.getElementById('msg');
            if (!msg) return;
            msg.className = 'msg ' + (d.success ? 'green' : 'red');
            msg.textContent = d.success ? 'Closed! PnL: $' + d.pnl.toFixed(2) : 'Error: ' + (d.error || 'unknown');
            msg.style.display = 'block';
            setTimeout(function() { msg.style.display = 'none'; }, 4000);
            fetchData();
        });
}

function switchTab(name) {
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) tabs[i].className = 'tab';
    var contents = document.querySelectorAll('.tab-content');
    for (var i = 0; i < contents.length; i++) contents[i].className = 'tab-content';
    var activeTab = document.querySelector('.tab[onclick*="' + name + '"]');
    if (activeTab) activeTab.className = 'tab active';
    var activeContent = document.getElementById('tab-' + name);
    if (activeContent) activeContent.className = 'tab-content active';
}

// Fetch immediately, then every 3 seconds
fetchData();
setInterval(fetchData, 3000);
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/all')
def api_all():
    try:
        return jsonify(get_all_data())
    except Exception as e:
        return jsonify({
            "price": get_current_price(),
            "stats": {"total_pnl": 0, "daily_pnl": 0, "total_trades": 0, "wins": 0, "win_rate": 0, "open_positions": 0, "unrealized_pnl": 0},
            "open": [], "closed": {"today": [], "yesterday": [], "history": []},
            "timestamp": fmt_ist(),
            "error": str(e)
        })


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
                        side = trade["side"]
                        size = trade["size"]
                        result = client.close_position("LONG" if side == "buy" else "SHORT", size)
                        close_success = result is not None
                        break
            except:
                pass

        trade = tm.close_trade(str(trade_id), current_price, "MANUAL_CLOSE" if close_success else "MANUAL_DB_ONLY")
        pnl = trade.get("pnl", 0) if trade else 0
        return redirect('/')
    except Exception as e:
        return redirect('/')


@app.route('/api/open-trades')
def api_open_trades():
    return jsonify(get_all_data()["open"])


@app.route('/api/closed-trades')
def api_closed_trades():
    return jsonify(get_all_data()["closed"])


@app.route('/api/stats')
def api_stats():
    return jsonify(get_all_data()["stats"])


@app.route('/api/health')
def api_health():
    data = get_all_data()
    return jsonify({"status": "ok", "price": data["price"], "timestamp": data["timestamp"],
                     "open_positions": data["stats"]["open_positions"],
                     "mode": "dry_run" if getattr(config, 'DRY_RUN', True) else "live"})


@app.route('/api/current-price')
def api_price():
    return jsonify({"price": get_current_price(), "timestamp": fmt_ist()})


@app.route('/api/close/<trade_id>')
def api_close_trade(trade_id):
    tm = get_trade_manager()
    if tm is None:
        return jsonify({"success": False, "error": "TradeManager not available"})

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
        return jsonify({"success": True, "pnl": round(pnl, 2)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
