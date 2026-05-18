import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()
c.execute("DELETE FROM trades WHERE id = 27")
conn.commit()
print("Deleted test trade")

c.execute("SELECT id, direction, entry_price, status FROM trades ORDER BY id DESC")
print("\nAll trades:")
for row in c.fetchall():
    print(f"  {row}")

conn.close()