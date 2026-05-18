from web_dashboard import get_stats, get_closed_trades

stats = get_stats()
closed = get_closed_trades()

print('=== STATS ===')
print('Total PnL:', stats['total_pnl'])
print('Daily PnL:', stats['daily_pnl'])
print('Today Closed:', stats['today_closed_pnl'], 'count:', stats['today_closed_count'])
print('Yesterday Closed:', stats['yesterday_closed_pnl'], 'count:', stats['yesterday_closed_count'])

print()
print('=== TODAY CLOSED ===')
for t in closed['today']:
    print(f"ID:{t['id']} Entry:{t['entry_price']} Exit:{t['exit_price']} PnL:{t['pnl_usd']}")

print()
print('=== YESTERDAY CLOSED ===')
for t in closed['yesterday']:
    print(f"ID:{t['id']} Entry:{t['entry_price']} Exit:{t['exit_price']} PnL:{t['pnl_usd']}")