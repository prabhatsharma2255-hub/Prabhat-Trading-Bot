"""
Trading Dashboard - SQLite-based trade logging and analytics

Tables:
- trades: Full trade history with all details
- bot_state: Current bot state snapshots
- signal_log: Every cycle's signals and decisions
"""

import sqlite3
import json
from datetime import datetime, date
from typing import Dict, List, Optional

DB_FILE = "trades.db"


def init_db():
    """Initialize database with full schema."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Create tables if not exist
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_entry TEXT,
        timestamp_exit TEXT,
        symbol TEXT,
        direction TEXT,
        regime TEXT,
        module_used TEXT,
        grade TEXT,
        entry_price REAL,
        exit_price REAL,
        size REAL,
        leverage REAL,
        stop_loss REAL,
        take_profit REAL,
        pnl_usd REAL,
        status TEXT DEFAULT 'closed',
        signals_fired TEXT,
        htf_aligned INTEGER,
        session TEXT,
        outcome TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        balance REAL,
        peak_balance REAL,
        current_drawdown_pct REAL,
        trades_today INTEGER,
        consecutive_losses INTEGER,
        regime TEXT,
        session TEXT,
        last_signal_time TEXT,
        open_positions INTEGER,
        review_mode INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS signal_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        regime_detected TEXT,
        module_triggered TEXT,
        signals_fired TEXT,
        signal_count INTEGER,
        trade_taken INTEGER,
        reason_skipped TEXT,
        htf_aligned INTEGER,
        htf_status TEXT,
        grade TEXT,
        direction TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Add missing columns if they don't exist (migration)
    try:
        c.execute("ALTER TABLE trades ADD COLUMN mode INTEGER DEFAULT 1")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE trades ADD COLUMN session TEXT")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE trades ADD COLUMN htf_aligned INTEGER DEFAULT 0")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'closed'")
    except:
        pass
    
    conn.commit()
    conn.close()


def log_trade(direction: str, entry_price: float, exit_price: float, 
              size: float, pnl: float, status: str, confidence: float,
              regime: str, signals: str = "", htf_aligned: bool = False,
              session: str = "", grade: str = "", module: str = "",
              outcome: str = "", leverage: int = 1, stop_loss: float = 0, take_profit: float = 0):
    """Log a trade to database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Add missing columns
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
    try:
        c.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'closed'")
    except:
        pass
    
    timestamp = datetime.now().isoformat()
    
    if status == "open":
        # First close any existing open positions with same direction
        c.execute("UPDATE trades SET status = 'closed', outcome = 'REPLACED' WHERE direction = ? AND status = 'open'", (direction,))
        
        c.execute('''INSERT INTO trades 
            (timestamp_entry, symbol, direction, regime, grade, module_used, 
             entry_price, size, pnl_usd, status, signals_fired, htf_aligned, session, leverage, stop_loss, take_profit)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (timestamp, "BTCUSD", direction, regime, grade, module,
             entry_price, size, pnl, status, signals, 1 if htf_aligned else 0, session, leverage, stop_loss, take_profit))
    
    elif status == "closed":
        # Update the most recent open trade with same direction
        c.execute('''UPDATE trades SET 
            timestamp_exit = ?, exit_price = ?, pnl_usd = ?, status = ?, outcome = ?
            WHERE id = (SELECT id FROM trades WHERE 
            direction = ? AND status = 'open' ORDER BY id DESC LIMIT 1)''',
            (timestamp, exit_price, pnl, status, outcome, direction))
    
    conn.commit()
    conn.close()


def log_signal_log(regime: str, module: str, signals: List[str], 
                   trade_taken: bool, reason_skipped: str = "",
                   htf_aligned: bool = False, htf_status: str = "",
                   grade: str = "", direction: str = "NONE"):
    """Log signal analysis for each cycle."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''INSERT INTO signal_log 
        (timestamp, regime_detected, module_triggered, signals_fired, signal_count,
         trade_taken, reason_skipped, htf_aligned, htf_status, grade, direction)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (datetime.now().isoformat(), regime, module, json.dumps(signals), len(signals),
         1 if trade_taken else 0, reason_skipped, 1 if htf_aligned else 0, 
         htf_status, grade, direction))
    
    conn.commit()
    conn.close()


def log_bot_state(balance: float, peak_balance: float, drawdown_pct: float,
                  trades_today: int, consecutive_losses: int, regime: str,
                  session: str, open_positions: int, review_mode: bool):
    """Log current bot state."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''INSERT INTO bot_state 
        (timestamp, balance, peak_balance, current_drawdown_pct, trades_today,
         consecutive_losses, regime, session, open_positions, review_mode)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (datetime.now().isoformat(), balance, peak_balance, drawdown_pct,
         trades_today, consecutive_losses, regime, session, open_positions,
         1 if review_mode else 0))
    
    conn.commit()
    conn.close()


def get_daily_stats() -> Dict:
    """Get today's trading statistics."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE date(timestamp_entry) = ?", (today,))
    count, pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE date(timestamp_entry) = ? AND pnl_usd > 0", (today,))
    wins, win_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE date(timestamp_entry) = ? AND pnl_usd < 0", (today,))
    losses, loss_pnl = c.fetchone()

    conn.close()

    return {
        "total_trades": count or 0,
        "total_pnl": pnl or 0,
        "wins": wins or 0,
        "losses": losses or 0,
        "win_pnl": win_pnl or 0,
        "loss_pnl": loss_pnl or 0,
        "win_rate": (wins / count * 100) if count and count > 0 else 0
    }


def get_all_time_stats() -> Dict:
    """Get all-time trading statistics."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades")
    count, total_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE pnl_usd > 0")
    wins, win_pnl = c.fetchone()

    c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE pnl_usd < 0")
    losses, loss_pnl = c.fetchone()

    conn.close()

    return {
        "total_trades": count or 0,
        "total_pnl": total_pnl or 0,
        "wins": wins or 0,
        "losses": losses or 0,
        "win_pnl": win_pnl or 0,
        "loss_pnl": loss_pnl or 0,
        "win_rate": (wins / count * 100) if count and count > 0 else 0
    }


def get_recent_trades(limit: int = 20) -> List:
    """Get recent trades."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    trades = c.fetchall()
    conn.close()
    return trades


def get_open_trades() -> List:
    """Get currently open trades."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE status = 'open'")
    trades = c.fetchall()
    conn.close()
    return trades


def get_signal_log(limit: int = 100) -> List:
    """Get recent signal logs."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM signal_log ORDER BY id DESC LIMIT ?", (limit,))
    logs = c.fetchall()
    conn.close()
    return logs


init_db()