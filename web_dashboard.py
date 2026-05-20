#!/usr/bin/env python3
"""Web Dashboard - Real-time with SSE + REST API"""

from flask import Flask, render_template_string, request, redirect, jsonify, Response
import requests
import os
import sys
import time
import threading
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from trade_manager import TradeManager
except:
    TradeManager = None

try:
    import config
    DRY_RUN = getattr(config, "DRY_RUN", True)
    BYBIT_KEY = getattr(config, "BYBIT_API_KEY", "")
except:
    DRY_RUN = True
    BYBIT_KEY = ""

BOT_STATE_FILE = "bot_state.json"

_connected = False

IST = timedelta(hours=5, minutes=30)

def now_ist():
    return datetime.now(timezone.utc) + IST

def fmt_ist(dt=None):
    dt = dt or now_ist()
    return dt.strftime("%Y-%m-%d %H:%M:%S IST")

app = Flask(__name__)

_last_price = [0]
_price_lock = threading.Lock()
_last_event_id = [0]

def _fetch_price():
    while True:
        try:
            r = requests.get("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", timeout=5)
            data = r.json()
            result = data.get("result", {}) if data else {}
            tickers = result.get("list") if isinstance(result, dict) else None
            if tickers:
                price = float(tickers[0].get("lastPrice", 0))
                with _price_lock:
                    _last_price[0] = price
        except:
            pass
        time.sleep(5)

def get_current_price():
    with _price_lock:
        return _last_price[0]


def get_live_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", timeout=3)
        data = r.json()
        result = data.get("result", {}) if data else {}
        tickers = result.get("list") if isinstance(result, dict) else None
        if tickers:
            return float(tickers[0].get("lastPrice", 0))
    except:
        pass
    return get_current_price()

def get_trade_manager():
    if TradeManager is None:
        return None
    return TradeManager()

def get_bot_state():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BOT_STATE_FILE)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except:
        pass
    return None

def get_all_data():
    price = get_live_price()
    bot_state = get_bot_state()
    tm = get_trade_manager()

    open_trades = []
    if bot_state and "open_positions" in bot_state:
        open_trades = bot_state["open_positions"]
    elif tm:
        db_open = tm.get_open_trades()
        if db_open:
            open_trades = db_open

    if tm:
        closed_trades = tm.get_closed_trades()
    else:
        closed_trades = []

    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl", 0) or 0) > 0)
    total_closed = len(closed_trades)
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    today = now_ist().date()
    today_closed = [t for t in closed_trades if t.get("close_time") and
                   datetime.fromisoformat(t["close_time"]).date() == today]
    daily_pnl = sum(t.get("pnl", 0) or 0 for t in today_closed)

    unrealized = 0
    open_list = []

    for t in open_trades:
        if "pnl" in t:
            lev = t.get("leverage", 1) or 1
            sz = t.get("size", 0) or 0
            entry = t.get("entry_price", 0)
            pnl_val = t.get("pnl", 0) or 0
            direction = t.get("direction", t.get("side", "sell"))
            if isinstance(direction, str) and direction.lower() in ["buy", "long"]:
                unrealized += (price - entry) * sz * lev
            else:
                unrealized += (entry - price) * sz * lev
            open_list.append({
                "id": t.get("trade_id", t.get("id", "")),
                "direction": direction if isinstance(direction, str) else ("LONG" if direction == 1 else "SHORT"),
                "entry": entry, "size": sz, "leverage": lev,
                "sl": t.get("stop_loss", 0), "tp": t.get("tp", t.get("take_profit_2", 0)),
                "pnl": round(pnl_val, 2)
            })
        else:
            side = t.get("side", "sell")
            lev = t.get("leverage", 1) or 1
            sz = t.get("size", 0) or 0
            entry = t.get("entry_price", 0)
            if side == "buy":
                upnl = (price - entry) * sz * lev
            else:
                upnl = (entry - price) * sz * lev
            open_list.append({
                "id": t.get("id", ""),
                "direction": "LONG" if side == "buy" else "SHORT",
                "entry": entry, "size": sz, "leverage": lev,
                "sl": t.get("sl", 0), "tp": t.get("tp", 0),
                "pnl": round(upnl, 2)
            })

    # Closed trades grouped by day
    today_c, yesterday_c, history_c = [], [], []
    yesterday = today - timedelta(days=1)
    for trade in closed_trades:
        ct = trade.get("close_time", "")
        if not ct:
            continue
        try:
            td = datetime.fromisoformat(ct).date()
        except:
            continue
        lev = trade.get("leverage", 1) or 1
        t = {
            "id": trade.get("id", ""),
            "direction": "LONG" if trade.get("side") in ["buy", "long"] else "SHORT",
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("close_price") or 0,
            "size": trade.get("size", 0) or 0,
            "leverage": lev,
            "pnl_usd": trade.get("pnl") or 0,
            "result": trade.get("close_reason", ""),
            "time": ct
        }
        if td == today:
            today_c.append(t)
        elif td == yesterday:
            yesterday_c.append(t)
        else:
            history_c.append(t)

    return {
        "price": price,
        "stats": {
            "total_pnl": round(total_pnl, 2),
            "daily_pnl": round(daily_pnl, 2),
            "total_trades": total_closed,
            "wins": wins,
            "win_rate": round(win_rate, 1),
            "open_positions": len(open_trades),
            "unrealized_pnl": round(unrealized, 2),
            "dry_run": DRY_RUN
        },
        "open": open_list,
        "closed": {"today": today_c, "yesterday": yesterday_c, "history": history_c},
        "timestamp": fmt_ist()
    }

HTML = """<!DOCTYPE html>
<html><head><title>Delta Trading Bot</title><meta charset=utf-8>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial;background:#0a0a0f;color:#ddd;padding:20px}
.container{max-width:1200px;margin:0 auto}
h1{color:#0c6;text-align:center;font-size:20px;margin-bottom:12px;letter-spacing:1px}
.top-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;flex-wrap:wrap;gap:8px}
.price-box{font-size:22px;color:#fa0;font-weight:bold}
.status-badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:4px 10px;border-radius:12px;background:#222}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.green{background:#0c6;box-shadow:0 0 6px #0c6;animation:pulse 2s infinite}
.dot.red{background:#f44}.dot.yellow{background:#fa0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.change{font-size:13px;font-weight:normal;margin-left:8px}
.dry-badge{background:#333;color:#fa0;border:1px solid #fa0;font-size:11px;padding:3px 8px;border-radius:8px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-bottom:20px}
.stat{background:#151520;padding:12px;border-radius:8px;text-align:center;border:1px solid #222}
.stat label{display:block;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.stat .val{font-size:18px;font-weight:bold}.green{color:#0c6}.red{color:#f44}
.section-title{color:#0c6;font-size:14px;border-bottom:1px solid #222;padding:12px 0 6px 0;margin:18px 0 8px 0;display:flex;justify-content:space-between}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#151520;color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;padding:8px 6px;text-align:left;border-bottom:1px solid #222}
td{padding:8px 6px;border-bottom:1px solid #151520}.long{color:#0c6}.short{color:#f44}
.btn{background:#f44;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:11px}
.btn:hover{opacity:0.8}.btn:disabled{opacity:0.3;cursor:default}
.empty{text-align:center;color:#444;padding:16px}
.msg{padding:10px 16px;border-radius:6px;margin-bottom:12px;text-align:center;font-size:13px;display:none}
.msg.success{background:#0c622;color:#0c6;display:block}.msg.error{background:#442;color:#f44;display:block}
.tab-bar{display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap}
.tab{background:#151520;color:#888;border:1px solid #222;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px}
.tab.active{background:#0c6;color:#000;border-color:#0c6;font-weight:bold}.tab-content{display:none}.tab-content.active{display:block}
.sse-indicator{font-size:10px;color:#444;float:right}
#footer{text-align:center;color:#333;font-size:11px;margin-top:20px}
.squeeze-alert{border:1px solid #fa0;padding:8px 12px;border-radius:6px;margin-bottom:12px;font-size:13px;background:#151520;display:none}
.squeeze-alert.active{display:block}
@media(max-width:600px){body{padding:10px}.stats{grid-template-columns:repeat(3,1fr)}.stat{padding:8px}.stat .val{font-size:14px}table{font-size:11px}th,td{padding:5px 3px}}
</style></head><body><div class=container>
<h1>BYBIT TRADING BOT</h1>
<div class=top-bar>
<div class=price-box>BTC/USD: $<span id=price>--</span><span class=change id=change></span></div>
<span class=status-badge><span class="dot green" id=status-dot></span><span id=status-text>connecting</span></span>
<span id=dry-badge></span>
<span class=sse-indicator id=sse-ind>SSE</span>
</div>
<div id=msg class=msg></div>
<div id=squeeze class=squeeze-alert></div>
<div class=stats>
<div class=stat><label>Total PnL</label><div class="val" id=s-total>$0</div></div>
<div class=stat><label>Unrealized</label><div class="val" id=s-unreal>$0</div></div>
<div class=stat><label>Daily PnL</label><div class="val" id=s-daily>$0</div></div>
<div class=stat><label>Trades</label><div class=val id=s-trades>0</div></div>
<div class=stat><label>Win Rate</label><div class=val id=s-winrate>0%</div></div>
<div class=stat><label>Open</label><div class=val id=s-open>0</div></div>
</div>
<div class=section-title>Open Positions <span id=open-cnt style="color:#888;font-weight:normal">(0)</span></div>
<table><thead><tr><th>Dir</th><th>Entry</th><th>Size</th><th>Lev</th><th>SL</th><th>TP</th><th>PnL</th><th></th></tr></thead><tbody id=open-body><tr><td colspan=8 class=empty>No open positions</td></tr></tbody></table>
<div class=tab-bar>
<div class="tab active" onclick=switchTab("today")>Today <span id=tab-c-today>0</span></div>
<div class=tab onclick=switchTab("yesterday")>Yesterday <span id=tab-c-yest>0</span></div>
<div class=tab onclick=switchTab("all")>All Closed <span id=tab-c-all>0</span></div>
</div>
<div id=tab-today class="tab-content active">
<div class=section-title>Today's Closed Trades</div>
<table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id=today-body><tr><td colspan=8 class=empty>No trades</td></tr></tbody></table></div>
<div id=tab-yesterday class=tab-content>
<div class=section-title>Yesterday</div>
<table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id=yesterday-body><tr><td colspan=8 class=empty>No trades</td></tr></tbody></table></div>
<div id=tab-all class=tab-content>
<div class=section-title>All Closed Trades</div>
<table><thead><tr><th>Dir</th><th>Entry</th><th>Exit</th><th>Size</th><th>Lev</th><th>PnL</th><th>Result</th><th>Time</th></tr></thead><tbody id=all-body><tr><td colspan=8 class=empty>No trades</td></tr></tbody></table></div>
<div id=footer></div>
</div>
<script>
var lastPrice=0;
var eventSource=null;
function s(id,v,pnl){
  var el=document.getElementById(id);
  if(!el)return;
  el.textContent=v;
  if(pnl!==undefined)el.className="val "+(pnl>=0?"green":"red");
}
function p(d){
  if(!d||!d.stats)return;
  var st=d.stats;
  s("s-total","$"+(st.total_pnl||0).toFixed(2),st.total_pnl);
  s("s-unreal","$"+(st.unrealized_pnl||0).toFixed(2),st.unrealized_pnl);
  s("s-daily","$"+(st.daily_pnl||0).toFixed(2),st.daily_pnl);
  document.getElementById("s-trades").textContent=st.total_trades||0;
  document.getElementById("s-winrate").textContent=(st.win_rate||0)+"%";
  document.getElementById("s-open").textContent=st.open_positions||0;
  if(st.dry_run){
    var b=document.getElementById("dry-badge");
    if(b)b.innerHTML='<span class=dry-badge>DRY RUN</span>';
  }
  var p=d.price||0;
  var pe=document.getElementById("price");
  if(pe)pe.textContent=p>0?p.toFixed(2):"--";
  var ch=document.getElementById("change");
  if(ch&&lastPrice>0&&p>0){
    var diff=p-lastPrice;
    ch.textContent=(diff>=0?"+":"")+diff.toFixed(2)+" ("+(diff>=0?"+":"")+(diff/lastPrice*100).toFixed(2)+"%)";
    ch.style.color=diff>=0?"#0c6":"#f44";
  }
  lastPrice=p;
  var dot=document.getElementById("status-dot");
  var txt=document.getElementById("status-text");
  if(dot)dot.className="dot green";
  if(txt)txt.textContent="live";
  var ol=d.open||[];
  document.getElementById("open-cnt").textContent="("+ol.length+")";
  var ob=document.getElementById("open-body");
  if(ol.length){
    ob.innerHTML=ol.map(function(t){
      var c=t.direction==="LONG"?"long":"short";
      return "<tr><td class="+c+">"+(t.direction||"")+"</td><td>$"+(t.entry||0).toFixed(0)
        +"</td><td>"+(t.size||0).toFixed(4)+"</td><td>"+(t.leverage||0)+"x</td><td>$"+(t.sl||0).toFixed(0)
        +"</td><td>$"+(t.tp||0).toFixed(0)+"</td><td class="+(t.pnl>=0?"green":"red")+">$"+(t.pnl||0).toFixed(2)
        +'</td><td><button onclick=closeTrade("'+(t.id||"")+'") class=btn>X</button></td></tr>';
    }).join("");
  }else{
    ob.innerHTML='<tr><td colspan=8 class=empty>No open positions</td></tr>';
  }
  var cl=d.closed||{};
  var tl=cl.today||[];
  var yl=cl.yesterday||[];
  var al=[].concat(tl,yl,cl.history||[]);
  document.getElementById("today-body").innerHTML=tl.length?tl.map(function(x){
    var c=x.direction==="LONG"?"long":"short";
    return "<tr><td class="+c+">"+(x.direction||"")+"</td><td>$"+(x.entry_price||0).toFixed(0)
      +"</td><td>$"+(x.exit_price||0).toFixed(0)+"</td><td>"+(x.size||0).toFixed(4)
      +"</td><td>"+(x.leverage||0)+"x</td><td class="+((x.pnl_usd||0)>=0?"green":"red")+">$"+(x.pnl_usd||0).toFixed(2)
      +"</td><td>"+(x.result||"")+"</td><td>"+((x.time||"").substring(0,16))+"</td></tr>";
  }).join(""):'<tr><td colspan=8 class=empty>No trades</td></tr>';
  document.getElementById("yesterday-body").innerHTML=yl.length?yl.map(function(x){
    var c=x.direction==="LONG"?"long":"short";
    return "<tr><td class="+c+">"+(x.direction||"")+"</td><td>$"+(x.entry_price||0).toFixed(0)
      +"</td><td>$"+(x.exit_price||0).toFixed(0)+"</td><td>"+(x.size||0).toFixed(4)
      +"</td><td>"+(x.leverage||0)+"x</td><td class="+((x.pnl_usd||0)>=0?"green":"red")+">$"+(x.pnl_usd||0).toFixed(2)
      +"</td><td>"+(x.result||"")+"</td><td>"+((x.time||"").substring(0,16))+"</td></tr>";
  }).join(""):'<tr><td colspan=8 class=empty>No trades</td></tr>';
  document.getElementById("all-body").innerHTML=al.length?al.map(function(x){
    var c=x.direction==="LONG"?"long":"short";
    return "<tr><td class="+c+">"+(x.direction||"")+"</td><td>$"+(x.entry_price||0).toFixed(0)
      +"</td><td>$"+(x.exit_price||0).toFixed(0)+"</td><td>"+(x.size||0).toFixed(4)
      +"</td><td>"+(x.leverage||0)+"x</td><td class="+((x.pnl_usd||0)>=0?"green":"red")+">$"+(x.pnl_usd||0).toFixed(2)
      +"</td><td>"+(x.result||"")+"</td><td>"+((x.time||"").substring(0,16))+"</td></tr>";
  }).join(""):'<tr><td colspan=8 class=empty>No trades</td></tr>';
  document.getElementById("tab-c-today").textContent=tl.length;
  document.getElementById("tab-c-yest").textContent=yl.length;
  document.getElementById("tab-c-all").textContent=al.length;
  document.getElementById("footer").textContent=d.timestamp||"";
  var ind=document.getElementById("sse-ind");
  if(ind)ind.textContent="SSE ●";
}
function closeTrade(id){
  if(!id)return;
  fetch("/api/close/"+encodeURIComponent(id)).then(function(r){return r.json()}).then(function(d){
    var m=document.getElementById("msg");
    if(!m)return;
    m.className="msg "+(d.success?"success":"error");
    m.textContent=d.success?"Closed! PnL: $"+((d.pnl||0).toFixed(2)):"Error: "+(d.error||"unknown");
    m.style.display="block";
    setTimeout(function(){m.style.display="none"},4000);
  }).catch(function(){var m=document.getElementById("msg");if(m){m.className="msg error";m.textContent="Request failed";m.style.display="block";setTimeout(function(){m.style.display="none"},3000);}});
}
function switchTab(n){
  document.querySelectorAll(".tab").forEach(function(t){t.classList.remove("active")});
  document.querySelectorAll(".tab-content").forEach(function(c){c.classList.remove("active")});
  var at=document.querySelector('.tab[onclick*="'+n+'"]');
  if(at)at.classList.add("active");
  var ac=document.getElementById("tab-"+n);
  if(ac)ac.classList.add("active");
}
function connectSSE(){
  if(eventSource)eventSource.close();
  eventSource=new EventSource("/api/stream");
  eventSource.onmessage=function(e){
    try{var d=JSON.parse(e.data);p(d);}
    catch(err){console.error(err);}
  };
  eventSource.onerror=function(){
    var ind=document.getElementById("sse-ind");
    if(ind)ind.textContent="RECONNECTING...";
    setTimeout(connectSSE,5000);
  };
}
connectSSE();
</script></body></html>"""


@app.route('/')
def index():
    try:
        data = get_all_data()
        price_val = data.get("price", 0) or 0
        st = data.get("stats", {})
        dry = st.get("dry_run", False)

        lines = []
        for line in HTML.split('\n'):
            if 'id=price' in line and '--' in line:
                line = line.replace('id=price>--', 'id=price>' + ("%.2f" % price_val if price_val else '--'))
            if 'id=dry-badge' in line and dry:
                line = line.replace('id=dry-badge></span>', 'id=dry-badge></span><span class=dry-badge>DRY RUN</span>')
            lines.append(line)
        html = '\n'.join(lines)
        return html
    except Exception as e:
        return HTML


@app.route('/api/stream')
def api_stream():
    def generate():
        while True:
            try:
                data = get_all_data()
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error':str(e)})}\n\n"
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/all')
def api_all():
    return jsonify(get_all_data())


@app.route('/api/open-trades')
def api_open():
    return jsonify(get_all_data()["open"])


@app.route('/api/closed-trades')
def api_closed():
    return jsonify(get_all_data()["closed"])


@app.route('/api/stats')
def api_stats():
    return jsonify(get_all_data()["stats"])


@app.route('/api/health')
def api_health():
    data = get_all_data()
    return jsonify({
        "status": "ok",
        "price": data["price"],
        "timestamp": data["timestamp"],
        "open_positions": data["stats"]["open_positions"],
        "mode": "dry_run" if DRY_RUN else "live"
    })


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
        trade = tm.close_trade(str(trade_id), current_price, "MANUAL_CLOSE")
        pnl = trade.get("pnl", 0) if trade else 0
        return jsonify({"success": True, "pnl": round(pnl, 2)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# Price updater runs in background
threading.Thread(target=_fetch_price, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)