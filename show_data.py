from web_dashboard import get_stats, get_closed_trades

s = get_stats()
c = get_closed_trades()

print('=== TODAY (Closed Today) ===')
for t in c['today']:
    print(f"ID {t['id']}: Entry {t['entry_price']} Exit {t['exit_price']} PnL {t['pnl_usd']} Outcome {t['outcome']} Setup {t['signals_fired']}")

print('\n=== YESTERDAY ===')
for t in c['yesterday']:
    print(f"ID {t['id']}: Entry {t['entry_price']} Exit {t['exit_price']} PnL {t['pnl_usd']} Outcome {t['outcome']} Setup {t['signals_fired']}")

print(f'\n=== STATS ===')
print(f'Total PnL: {s["total_pnl"]}')
print(f'Today Closed: {s["today_closed_pnl"]}')
print(f'Yesterday Closed: {s["yesterday_closed_pnl"]}')
print(f'Win Rate: {s["win_rate"]}%')