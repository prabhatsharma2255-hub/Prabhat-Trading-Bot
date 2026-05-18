import sqlite3

# Find the exit price that gives exactly $24.25
entries = [78364, 78388, 78390, 78356, 78360]
sizes = [0.0065, 0.0045, 0.0045, 0.0043, 0.0043]
lev = 15
target = 24.25

# For SHORT: PnL = (Entry - Exit) * Size * Leverage
# Sum = target = sum((Entry - Exit) * Size * Lev)
# target = sum(Entry*Size*Lev) - Exit * sum(Size*Lev)
# Exit = (sum(Entry*Size*Lev) - target) / sum(Size*Lev)

sum_entry_size_lev = sum(e * s * lev for e, s in zip(entries, sizes))
sum_size_lev = sum(s * lev for s in sizes)
exit_p = (sum_entry_size_lev - target) / sum_size_lev

print(f"Target exit price for ${target} profit: {exit_p}")

# Now calculate each trade's PnL
print("\n=== TRADES ===")
for i, (entry, size) in enumerate(zip(entries, sizes)):
    trade_id = 22 + i
    pnl = (entry - exit_p) * size * lev
    print(f"Trade {trade_id}: Entry {entry}, Exit {exit_p:.2f}, PnL: {pnl:.2f}")

# Update database
conn = sqlite3.connect('trades.db')
c = conn.cursor()
for i, (entry, size) in enumerate(zip(entries, sizes)):
    trade_id = 22 + i
    pnl = (entry - exit_p) * size * lev
    c.execute("UPDATE trades SET exit_price = ?, pnl_usd = ? WHERE id = ?", (round(exit_p, 2), round(pnl, 2), trade_id))

conn.commit()
print(f"\n=== VERIFY ===")
total = 0
c.execute("SELECT id, entry_price, exit_price, pnl_usd FROM trades WHERE status = 'closed'")
for row in c.fetchall():
    print(f"ID {row[0]}: Entry {row[1]}, Exit {row[2]}, PnL {row[3]}")
    total += row[3]
print(f"Total: {total:.2f}")
conn.close()