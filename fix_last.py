import sqlite3
from datetime import datetime

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# The trade we just closed manually via dashboard
# Entry 76994.5, Exit at current price 76765, PnL +2.03 (profit)
# Update the existing open trade to closed

c.execute("UPDATE trades SET status='closed', exit_price=76765.0, pnl_usd=2.03, outcome='MANUAL_CLOSE', timestamp_exit='2026-05-18T12:12:35' WHERE id=1")

conn.commit()

# Verify
print("=== ALL TRADES ===")
c.execute("SELECT id, direction, entry_price, exit_price, pnl_usd, status, outcome FROM trades ORDER BY id")
for row in c.fetchall():
    print(f"ID:{row[0]} {row[1]} Entry:{row[2]} Exit:{row[3]} PnL:{row[4]} Status:{row[5]} Outcome:{row[6]}")

# Total
c.execute("SELECT SUM(pnl_usd) FROM trades")
print(f"\nTotal PnL: {c.fetchone()[0]}")

conn.close()