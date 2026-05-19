"""
Trade Manager - SQLite persistence for trades
Provides both standalone functions and a TradeManager class
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

DB = "trades.db"

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id TEXT PRIMARY KEY,
        symbol TEXT,
        side TEXT,
        size REAL,
        entry_price REAL,
        close_price REAL,
        tp REAL,
        sl REAL,
        leverage INTEGER DEFAULT 1,
        pnl REAL,
        status TEXT DEFAULT 'open',
        close_reason TEXT,
        open_time TEXT,
        close_time TEXT
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS pattern_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        regime TEXT,
        session TEXT,
        mode INTEGER DEFAULT 0,
        signals_count INTEGER DEFAULT 0,
        direction TEXT,
        pnl REAL,
        outcome TEXT
    )""")
    conn.commit()
    conn.close()

# ============================================================
# STANDALONE FUNCTIONS
# ============================================================

def save_trade(t):
    conn = sqlite3.connect(DB)
    conn.execute("""
    INSERT OR IGNORE INTO trades VALUES 
    (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (t['id'],t['symbol'],t['side'],t['size'],
     t['entry_price'],None,t.get('tp',0),t.get('sl',0),
     t.get('leverage',1),None,'open',None,
     str(now_ist()),None))
    conn.commit()
    conn.close()

def close_trade(trade_id, close_price, reason):
    conn = sqlite3.connect(DB)
    cur = conn.execute(
        "SELECT * FROM trades WHERE id=?", (trade_id,))
    row = cur.fetchone()
    if row:
        columns = [desc[0] for desc in cur.description]
        t = dict(zip(columns, row))
        entry = t.get('entry_price', 0) or 0
        size = t.get('size', 0) or 0
        lev = t.get('leverage', 1) or 1
        side = t.get('side', 'sell')
        if side in ['buy','long']:
            pnl = (close_price - entry) * size * lev
        else:
            pnl = (entry - close_price) * size * lev
        conn.execute("""
        UPDATE trades SET 
        status='closed',
        close_price=?,
        pnl=?,
        close_reason=?,
        close_time=?
        WHERE id=?""",
        (close_price, pnl, reason,
         str(now_ist()), trade_id))
        conn.commit()
    conn.close()

def get_open():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='open'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_closed():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM trades 
        WHERE status='closed' 
        ORDER BY close_time DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ============================================================
# TRADEMANAGER CLASS (used by web_dashboard, trading_bot)
# ============================================================

class TradeManager:
    def __init__(self):
        init_db()

    def save_trade(self, trade_data: Dict) -> bool:
        try:
            conn = sqlite3.connect(DB)
            conn.execute("""
            INSERT OR IGNORE INTO trades 
            (id, symbol, side, size, entry_price, close_price, tp, sl, leverage, pnl, status, close_reason, open_time, close_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade_data.get("trade_id", trade_data.get("id", "")),
                trade_data.get("symbol", "BTCUSD"),
                trade_data.get("side", "buy"),
                trade_data.get("size", 0),
                trade_data.get("entry_price", 0),
                None,
                trade_data.get("tp", 0),
                trade_data.get("sl", 0),
                trade_data.get("leverage", 1),
                None,
                'open',
                None,
                trade_data.get("open_time", str(now_ist())),
                None
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"TradeManager save error: {e}")
            return False

    def close_trade(self, trade_id: str, close_price: float, close_reason: str = "manual", fees: float = 0) -> Optional[Dict]:
        try:
            conn = sqlite3.connect(DB)
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return None

            t = dict(row)
            entry = t.get('entry_price', 0) or 0
            size = t.get('size', 0) or 0
            lev = t.get('leverage', 1) or 1
            side = t.get('side', 'sell')

            if side in ['buy', 'long']:
                pnl = (close_price - entry) * size * lev
            else:
                pnl = (entry - close_price) * size * lev

            pnl -= fees

            conn.execute("""
            UPDATE trades SET 
                status='closed',
                close_price=?,
                pnl=?,
                close_reason=?,
                close_time=?
            WHERE id=?""",
            (close_price, pnl, close_reason, str(now_ist()), trade_id))
            conn.commit()
            conn.close()
            return {"pnl": pnl, "close_price": close_price, "close_reason": close_reason}
        except Exception as e:
            print(f"TradeManager close error: {e}")
            return None

    def get_open_trades(self) -> List[Dict]:
        return get_open()

    def get_all_open_trades(self) -> List[Dict]:
        return get_open()

    def get_closed_trades(self) -> List[Dict]:
        return get_closed()

    def get_all_trades(self) -> List[Dict]:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY open_time DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

init_db()
