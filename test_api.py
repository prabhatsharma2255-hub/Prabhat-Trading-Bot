from web_dashboard import app

with app.test_client() as client:
    # Test open trades API
    r1 = client.get('/api/open-trades')
    print("Open Trades API:", r1.json)
    
    # Test closed trades API
    r2 = client.get('/api/closed-trades')
    print("Closed Trades API:", r2.json["trades"][:2] if r2.json["trades"] else "None")
    
    # Test stats API
    r3 = client.get('/api/stats')
    print("Stats API:", r3.json["daily_pnl"], r3.json["total_pnl"])
    
    # Test current price API
    r4 = client.get('/api/current-price')
    print("Price API:", r4.json)