entries = [78364, 78388, 78390, 78356, 78360]
sizes = [0.0065, 0.0045, 0.0045, 0.0043, 0.0043]
leverage = 4
target_pnl = 24.25

total_entry_val = sum(e * s * leverage for e, s in zip(entries, sizes))
total_notional = sum(s * leverage for s in sizes)
exit_price = (total_entry_val - target_pnl) / total_notional

print(f"Total entry value: {total_entry_val}")
print(f"Total notional: {total_notional}")
print(f"Exit price for ${target_pnl} profit: ${exit_price:.2f}")

# Also check current exit at 78300
total_pnl_78300 = sum((e - 78300) * s * leverage for e, s in zip(entries, sizes))
print(f"PnL at exit $78300: ${total_pnl_78300:.2f}")