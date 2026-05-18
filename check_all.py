import sqlite3

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Show all
c.execute("SELECT * FROM trades ORDER BY id")
print("ALL TRADES:")
for row in c.fetchall():
    print(row)

# Check stats
c.execute("SELECT status, COUNT(*), SUM(pnl_usd) FROM trades GROUP BY status")
print("\nBY STATUS:")
for row in c.fetchall():
    print(f"  {row}")

conn.close()