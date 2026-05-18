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

for t in trades_to_add:
    direction, entry, exit_price, size, pnl, outcome, setup, t_entry, t_exit = t
    c.execute('''INSERT INTO trades 
        (timestamp_entry, symbol, direction, regime, grade, module_used, 
         entry_price, exit_price, size, pnl_usd, status, signals_fired, htf_aligned, session, leverage, stop_loss, take_profit)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (t_entry, "BTCUSD", direction, "bearish", setup, setup, entry, exit_price, size, pnl, "closed", setup, 0, "ny", 4, 0, 0))

conn.commit()
print(f"Added {len(trades_to_add)} trades")

c.execute("SELECT direction, entry_price, exit_price, pnl_usd, status, signals_fired FROM trades")
for r in c.fetchall():
    print(r)

conn.close()