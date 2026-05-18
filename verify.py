from web_dashboard import get_stats, get_current_price
import json

price = get_current_price()
print("Current Price:", price)

stats = get_stats()
print("Total PnL:", stats["total_pnl"])
print("Daily PnL (closed):", stats["daily_pnl"])
print("Open Positions:", stats["open_positions"])
print("Today Closed PnL:", stats["today_closed_pnl"])
print("Yesterday Closed PnL:", stats["yesterday_closed_pnl"])