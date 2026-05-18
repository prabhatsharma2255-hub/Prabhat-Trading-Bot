import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Delete stale trades (exit = 0 or NULL)
c.execute("DELETE FROM trades WHERE exit_price = 0 OR exit_price IS NULL")
conn.commit()

# Show remaining
c.execute("SELECT id, entry_price, exit_price, pnl_usd, status, outcome FROM trades")
print("=== CLEAN TRADES ===")
for row in c.fetchall():
    print(f"ID:{row[0]} Entry:{row[1]} Exit:{row[2]} PnL:{row[3]} Status:{row[4]} Outcome:{row[5]}")

conn.close()