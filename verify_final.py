from web_dashboard import get_stats, get_closed_trades, get_trades

s = get_stats()
c = get_closed_trades()
t = get_trades()

print("=== OPEN POSITIONS ===")
for tr in t:
    if tr['status'] == 'open':
        print(f"Entry: ${tr['entry_price']} | SL: ${tr['stop_loss']} | TP: ${tr['take_profit']} | PnL: ${tr.get('current_pnl', 0):.2f}")

print("\n=== CLOSED TODAY ===")
for tr in c['today']:
    print(f"Entry: ${tr['entry_price']} | Exit: ${tr['exit_price']} | PnL: ${tr['pnl_usd']} | {tr['outcome']}")

print("\n=== YESTERDAY ===")
for tr in c['yesterday']:
    print(f"Entry: ${tr['entry_price']} | Exit: ${tr['exit_price']} | PnL: ${tr['pnl_usd']} | {tr['outcome']}")

print(f"\n=== STATS ===")
print(f"Total PnL: ${s['total_pnl']}")
print(f"Today Closed: ${s['today_closed_pnl']}")
print(f"Yesterday Closed: ${s['yesterday_closed_pnl']}")
print(f"Open: {s['open_positions']}")