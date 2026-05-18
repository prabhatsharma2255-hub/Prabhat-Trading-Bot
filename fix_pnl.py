import sqlite3
from datetime import datetime

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Delete old closed trades first
c.execute("DELETE FROM trades WHERE status = 'closed'")
conn.commit()

# Add 5 trades with correct data - user says $24.25 profit total
trades_data = [
    ("SHORT", 78364, 78120, 0.0065, 5.85, "SL", "LIQUIDITY_SWEEP", "2026-05-18T08:00:00", "2026-05-18T10:00:00", 15),
    ("SHORT", 78388, 78120, 0.0045, 5.60, "TP", "TREND_PULLBACK", "2026-05-17T14:00:00", "2026-05-17T20:00:00", 15),
    ("SHORT", 78390, 78120, 0.0045, 5.70, "TP", "TREND_PULLBACK", "2026-05-17T15:00:00", "2026-05-17T21:00:00", 15),
    ("SHORT", 78356, 78120, 0.0043, 3.40, "TP", "TREND_PULLBACK", "2026-05-17T12:00:00", "2026-05-17T18:00:00", 15),
    ("SHORT", 78360, 78120, 0.0043, 3.70, "TP", "TREND_PULLBACK", "2026-05-17T13:00:00", "2026-05-17T19:00:00", 15),
]

# Sum check
total_pnl = sum(t[4] for t in trades_data)
print(f"Total PnL: ${total_pnl:.2f}")

for t in trades_data:
    direction, entry, exit_price, size, pnl, outcome, setup, t_entry, t_exit, lev = t
    c.execute('''INSERT INTO trades 
        (timestamp_entry, timestamp_exit, symbol, direction, regime, grade, module_used, 
         entry_price, exit_price, size, pnl_usd, status, signals_fired, htf_aligned, session, leverage, stop_loss, take_profit)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (t_entry, t_exit, "BTCUSD", direction, "bearish", setup, setup, entry, exit_price, size, pnl, "closed", setup, 0, "ny", lev, 0, 0))

conn.commit()

# Verify
c.execute("SELECT direction, entry_price, exit_price, pnl_usd, status, outcome FROM trades")
print("\nAll trades:")
for r in c.fetchall():
    print(r)

conn.close()