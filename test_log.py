import sys
sys.path.insert(0, '.')

import dashboard
from datetime import datetime

# Test logging an open trade
print("=== Testing Open Trade Log ===")
dashboard.log_trade(
    direction="SHORT",
    entry_price=77000.00,
    exit_price=0,
    size=0.001,
    pnl=0,
    status="open",
    confidence=80,
    regime="bearish",
    signals="TEST",
    htf_aligned=False,
    session="ny",
    grade="TEST_SETUP",
    module="TEST",
    leverage=5,
    stop_loss=77500,
    take_profit=76000
)

# Check database
import sqlite3
conn = sqlite3.connect('trades.db')
c = conn.cursor()
c.execute("SELECT id, direction, entry_price, size, status, signals_fired FROM trades ORDER BY id DESC LIMIT 3")
print("\nRecent trades in DB:")
for row in c.fetchall():
    print(f"  {row}")
conn.close()