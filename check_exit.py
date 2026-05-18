import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()

c.execute("SELECT id, direction, entry_price, exit_price, size, leverage, pnl_usd, signals_fired FROM trades WHERE status = 'closed'")
for row in c.fetchall():
    print(row)
conn.close()