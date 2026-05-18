import sqlite3
from datetime import datetime

conn = sqlite3.connect('trades.db')
c = conn.cursor()

print('=== ALL TRADES ===')
c.execute('SELECT id, direction, entry_price, exit_price, pnl_usd, status, timestamp_entry, timestamp_exit FROM trades ORDER BY id')
for row in c.fetchall():
    entry_date = row[6][:10] if row[6] else 'None'
    exit_date = row[7][:10] if row[7] else 'None'
    print(f'ID:{row[0]} Dir:{row[1]} Entry:{row[2]} Exit:{row[3]} PnL:{row[4]} Status:{row[5]} Entry:{entry_date} Exit:{exit_date}')

today = datetime.now().date()
print(f'\nToday is: {today}')

# What gets counted as today (by entry)
c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE status = 'closed' AND date(timestamp_entry) = date('now')")
r1 = c.fetchone()
print(f'By timestamp_entry: {r1[0]} trades, PnL: {r1[1]}')

# What gets counted as today (by exit)
c.execute("SELECT COUNT(*), SUM(pnl_usd) FROM trades WHERE status = 'closed' AND date(timestamp_exit) = date('now')")
r2 = c.fetchone()
print(f'By timestamp_exit: {r2[0]} trades, PnL: {r2[1]}')

conn.close()