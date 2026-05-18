"""
Simple REST API for trade data - serves trades to dashboard
"""
from flask import Flask, jsonify
import threading

app = Flask(__name__)

_trades = {"open": [], "closed": []}

def update_trades(open_trades, closed_trades):
    global _trades
    _trades["open"] = open_trades
    _trades["closed"] = closed_trades

@app.route("/api/trades")
def get_trades():
    return jsonify(_trades)

@app.route("/api/stats")
def get_stats():
    closed = _trades["closed"]
    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed)
    wins = len([t for t in closed if (t.get("pnl", 0) or 0) > 0])
    win_rate = (wins / len(closed) * 100) if closed else 0
    return jsonify({
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "open_count": len(_trades["open"]),
        "closed_count": len(closed)
    })

def run_api(port=5001):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)