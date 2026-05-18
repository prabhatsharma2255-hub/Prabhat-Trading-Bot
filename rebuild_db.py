import sqlite3
from datetime import datetime

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Delete everything and rebuild
c.execute("DELETE FROM trades")
conn.commit()

# Add ALL trades exactly as from your original dashboard data:
# Direction, Entry, Exit, Size, PnL, Outcome, Setup, EntryTime, ExitTime

all_trades = [
    # Today - open position
    (1, "SHORT", 76994.5, 0, 0, "open", "TREND_PULLBACK", "2026-05-18T10:16:37", None),
    
    # Today's closed (from your original data)
    (22, "SHORT", 78364, 78300, -1.5, "closed", "LIQUIDITY_SWEEP", "2026-05-18T08:00:00", "2026-05-18T10:00:00"),
    
    # Yesterday's trades (stale - never closed properly)
    (23, "SHORT", 78388, 0, 0, "closed", "TREND_PULLBACK", "2026-05-17T14:00:00", "2026-05-17T20:00:00"),
    (24, "SHORT", 78390, 0, 0, "closed", "TREND_PULLBACK", "2026-05-17T15:00:00", "2026-05-17T21:00:00"),
    (25, "SHORT", 78356, 0, 0, "closed", "TREND_PULLBACK", "2026-05-17T12:00:00", "2026-05-17T18:00:00"),
    (26, "SHORT", 78360, 0, 0, "closed", "TREND_PULLBACK", "2026-05-17T13:00:00", "2026-05-17T19:00:00"),
]

for trade_id, direction, entry, exit_p, pnl, status, setup, t_entry, t_exit in all_trades:
    c.execute("""INSERT INTO trades 
        (id, direction, entry_price, exit_price, pnl_usd, status, signals_fired, grade, timestamp_entry, timestamp_exit, regime, module_used, size, leverage, outcome)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trade_id, direction, entry, exit_p, pnl, status, setup, setup, t_entry, t_exit, "neutral", setup, 0.001, 5, "STALE" if exit_p == 0 else "closed"))

conn.commit()

# Show all trades
print("=== ALL TRADES IN DATABASE ===")
c.execute("SELECT id, direction, entry_price, exit_price, pnl_usd, status, signals_fired, outcome FROM trades ORDER BY id")
for row in c.fetchall():
    print(f"ID:{row[0]} Dir:{row[1]} Entry:{row[2]} Exit:{row[3]} PnL:{row[4]} Status:{row[5]} Setup:{row[6]} Outcome:{row[7]}")

conn.close()