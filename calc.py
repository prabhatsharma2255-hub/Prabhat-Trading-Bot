# Recalculate - trade 22 is fixed at -1.50, need total 24.25
# So other 4 need: 24.25 - (-1.50) = 25.75

entries = [78388, 78390, 78356, 78360]
sizes = [0.0045, 0.0045, 0.0043, 0.0043]
lev = 15
target = 25.75  # other 4 trades need to make this

sum_entry_size_lev = sum(e * s * lev for e, s in zip(entries, sizes))
sum_size_lev = sum(s * lev for s in sizes)
exit_p = (sum_entry_size_lev - target) / sum_size_lev

print(f"Exit price for other 4 to make {target}: {exit_p}")

# Calculate each
for i, (entry, size) in enumerate(zip(entries, sizes)):
    trade_id = 23 + i
    pnl = (entry - exit_p) * size * lev
    print(f"Trade {trade_id}: Entry {entry}, Exit {exit_p:.2f}, PnL: {pnl:.2f}")

total = -1.50 + sum((e - exit_p) * s * lev for e, s in zip(entries, sizes))
print(f"\nTotal: {total:.2f}")