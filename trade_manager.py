import sqlite3
from datetime import datetime

DB = "trades.db"

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
        leverage INTEGER,
        pnl REAL,
        status TEXT DEFAULT 'open',
        close_reason TEXT,
        open_time TEXT,
        close_time TEXT
    )""")
    conn.commit()
    conn.close()

def save_trade(t):
    conn = sqlite3.connect(DB)
    conn.execute("""
    INSERT OR IGNORE INTO trades VALUES 
    (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (t['id'],t['symbol'],t['side'],t['size'],
     t['entry_price'],None,t['tp'],t['sl'],
     t.get('leverage',1),None,'open',None,
     str(datetime.utcnow()),None))
    conn.commit()
    conn.close()

def close_trade(trade_id, close_price, reason):
    conn = sqlite3.connect(DB)
    cur = conn.execute(
        "SELECT * FROM trades WHERE id=?", (trade_id,))
    t = cur.fetchone()
    if t:
        entry = t[4]
        size = t[3]
        lev = t[8]
        side = t[2]
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
         str(datetime.utcnow()), trade_id))
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

init_db()