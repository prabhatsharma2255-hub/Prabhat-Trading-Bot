import sqlite3

exit_p = 78276.31

conn = sqlite3.connect('trades.db')
c = conn.cursor()

# Fix trades 23-26
entries = [78388, 78390, 78356, 78360]
sizes = [0.0045, 0.0045, 0.0043, 0.0043]
lev = 15

for i, (entry, size) in enumerate(zip(entries, sizes)):
    trade_id = 23 + i
    pnl = (entry - exit_p) * size * lev
    c.execute("UPDATE trades SET exit_price = ?, pnl_usd = ? WHERE id = ?", (round(exit_p, 2), round(pnl, 2), trade_id))

conn.commit()

# Verify
print("All closed trades:")
total = 0
c.execute("SELECT id, entry_price, exit_price, pnl_usd FROM trades WHERE status = 'closed'")
for row in c.fetchall():
    print(f"ID {row[0]}: Entry {row[1]}, Exit {row[2]}, PnL {row[3]}")
    total += row[3]
print(f"Total: {total}")

conn.close()