# Simple Trading Dashboard with SQLite Database
import sqlite3
import os
from datetime import datetime, date

DB_FILE = "trades.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        date TEXT,
        direction TEXT,
        entry_price REAL,
        exit_price REAL,
        size REAL,
        pnl REAL,
        status TEXT,
        confidence REAL,
        regime TEXT
    )''')
    conn.commit()
    conn.close()


def log_trade(direction, entry_price, exit_price, size, pnl, status, confidence, regime):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO trades (timestamp, date, direction, entry_price, exit_price, size, pnl, status, confidence, regime)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (datetime.now().isoformat(), date.today().isoformat(), direction, entry_price, exit_price, size, pnl, status, confidence, regime))
    conn.commit()
    conn.close()


def get_daily_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE date = ?", (today,))
    count, pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE date = ? AND pnl > 0", (today,))
    wins, win_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE date = ? AND pnl < 0", (today,))
    losses, loss_pnl = c.fetchone()

    conn.close()

    return {
        "total_trades": count or 0,
        "total_pnl": pnl or 0,
        "wins": wins or 0,
        "losses": losses or 0,
        "win_pnl": win_pnl or 0,
        "loss_pnl": loss_pnl or 0
    }


def get_all_time_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades")
    count, total_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE pnl > 0")
    wins, win_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE pnl < 0")
    losses, loss_pnl = c.fetchone()

    conn.close()

    return {
        "total_trades": count or 0,
        "total_pnl": total_pnl or 0,
        "wins": wins or 0,
        "losses": losses or 0,
        "win_pnl": win_pnl or 0,
        "loss_pnl": loss_pnl or 0
    }


def get_recent_trades(limit=20):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    trades = c.fetchall()
    conn.close()
    return trades


init_db()
print("Database initialized: trades.db")