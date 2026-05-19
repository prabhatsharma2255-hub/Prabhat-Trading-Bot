import sqlite3
from datetime import datetime

trades_to_add = [
    # (direction, entry, exit, size, pnl, outcome, setup, timestamp_entry, timestamp_exit)
    ("SHORT", 78364, 78300, 0.0065, -1.50, "SL", "LIQUIDITY_SWEEP", "2026-05-18T10:00:00", "2026-05-18T10:30:00"),
    ("SHORT", 78388, 78364, 0.0045, -0.11, "STALE_CLEANUP", "TREND_PULLBACK", "2026-05-17T15:00:00", "2026-05-18T08:00:00"),
    ("SHORT", 78390, 78364, 0.0045, -0.12, "STALE_CLEANUP", "TREND_PULLBACK", "2026-05-17T16:00:00", "2026-05-18T08:00:00"),
    ("SHORT", 78356, 78364, 0.0043, 0.03, "STALE_CLEANUP", "TREND_PULLBACK", "2026-05-17T14:00:00", "2026-05-18T08:00:00"),
    ("SHORT", 78360, 78364, 0.0043, 0.02, "STALE_CLEANUP", "TREND_PULLBACK", "2026-05-17T14:30:00", "2026-05-18T08:00:00"),
]

conn = sqlite3.connect('trades.db')
c = conn.cursor()

for i, t in enumerate(trades_to_add):
    direction, entry, exit_price, size, pnl, outcome, setup, t_entry, t_exit = t
    trade_id = f"restored_{i}_{t_entry.replace(':', '').replace('-', '')}"
    side = "buy" if direction == "LONG" else "sell"
    c.execute('''INSERT INTO trades
        (id, symbol, side, size, entry_price, close_price, tp, sl, leverage, pnl, status, close_reason, open_time, close_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (trade_id, "BTCUSD", side, size, entry, exit_price, 0, 0, 4, pnl, "closed", outcome, t_entry, t_exit))

conn.commit()
print(f"Added {len(trades_to_add)} trades")

c.execute("SELECT id, side, entry_price, close_price, pnl, status, close_reason FROM trades WHERE id LIKE 'restored_%'")
for r in c.fetchall():
    print(r)

conn.close()
