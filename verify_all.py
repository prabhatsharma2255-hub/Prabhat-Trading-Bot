from web_dashboard import get_stats, get_closed_trades, get_trades

s = get_stats()
c = get_closed_trades()
t = get_trades()

print("=== OPEN ===")
for tr in t:
    if tr['status'] == 'open':
        print(f"Entry:{tr['entry_price']} PnL:{tr.get('current_pnl', 0):.2f}")

print("=== TODAY CLOSED ===")
for tr in c['today']:
    print(f"Entry:{tr['entry_price']} Exit:{tr['exit_price']} PnL:{tr['pnl_usd']}")

print("=== YESTERDAY ===")
for tr in c['yesterday']:
    print(f"Entry:{tr['entry_price']} Exit:{tr['exit_price']} PnL:{tr['pnl_usd']}")

print(f"=== STATS ===")
print(f"Total:{s['total_pnl']}")
print(f"Open:{s['open_positions']}")