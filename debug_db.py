import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('trades.db')
c = conn.cursor()

print("=== All trades ===")
c.execute('SELECT id, direction, status, timestamp_entry, timestamp_exit, pnl_usd FROM trades')
for r in c.fetchall():
    print(r)

today = datetime.now().date()
yesterday = today - timedelta(days=1)

print(f"\n=== Date check ===")
print(f"Today: {today}")
print(f"Yesterday: {yesterday}")

c.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_entry) = ?", (today,))
print(f"Today closed: {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_entry) = ?", (yesterday,))
print(f"Yesterday closed: {c.fetchone()[0]}")

c.execute("SELECT COUNT(*) FROM trades WHERE status = 'closed' AND date(timestamp_entry) < ?", (yesterday,))
print(f"History closed: {c.fetchone()[0]}")

conn.close()