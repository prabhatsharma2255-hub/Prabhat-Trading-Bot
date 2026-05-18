import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Fix Trade 22 - LIQUIDITY_SWEEP that hit SL at $78300 with -$1.50
c.execute("UPDATE trades SET exit_price = 78300, pnl_usd = -1.50 WHERE id = 22")

conn.commit()

# Verify
c.execute("SELECT id, entry_price, exit_price, pnl_usd, signals_fired FROM trades WHERE status = 'closed'")
print("Fixed trades:")
total = 0
for row in c.fetchall():
    print(f"ID:{row[0]} Entry:{row[1]} Exit:{row[2]} PnL:{row[3]} Setup:{row[4]}")
    total += row[3]
print(f"Total PnL: {total}")

conn.close()