import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()

c.execute("SELECT id, direction, entry_price, size, leverage, stop_loss, take_profit FROM trades WHERE status = 'open'")
row = c.fetchone()
if row:
    print("OPEN POSITION:")
    print(f"  ID: {row[0]}")
    print(f"  Direction: {row[1]}")
    print(f"  Entry: {row[2]}")
    print(f"  Size: {row[3]}")
    print(f"  Leverage: {row[4]}x")
    print(f"  Stop Loss: {row[5]}")
    print(f"  Take Profit: {row[6]}")
else:
    print("No open position")

conn.close()