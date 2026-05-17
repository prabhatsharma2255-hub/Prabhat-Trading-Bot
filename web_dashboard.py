# Flask Web Dashboard for Trading Bot
from flask import Flask, render_template_string
import dashboard

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Trading Bot Dashboard</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial; margin: 20px; background: #1a1a2e; color: #eee; }
        .header { text-align: center; margin-bottom: 30px; }
        h1 { color: #00d4ff; }
        .stats-container { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-box {
            background: #16213e; padding: 20px; border-radius: 10px; min-width: 200px;
            border: 1px solid #0f3460; flex: 1;
        }
        .stat-box h3 { margin: 0 0 10px 0; color: #e94560; }
        .stat-box .value { font-size: 28px; font-weight: bold; }
        .profit { color: #00ff88; }
        .loss { color: #ff4757; }
        table { width: 100%; border-collapse: collapse; background: #16213e; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { background: #0f3460; color: #00d4ff; }
        tr:hover { background: #1f4068; }
        .status-open { color: #ffa502; }
        .status-closed { color: #00ff88; }
        .refresh { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI Trading Bot Dashboard</h1>
        <p>Delta Exchange - BTCUSD Perpetual</p>
    </div>

    <div class="stats-container">
        <div class="stat-box">
            <h3>Today's P&L</h3>
            <div class="value {{ 'profit' if daily_pnl > 0 else 'loss' if daily_pnl < 0 else '' }}">
                ${{ "%.2f"|format(daily.total_pnl) }}
            </div>
            <p>{{ daily.total_trades }} trades</p>
        </div>
        <div class="stat-box">
            <h3>Today's Wins/Losses</h3>
            <div class="value">
                <span style="color:#00ff88">{{ daily.wins }}W</span> /
                <span style="color:#ff4757">{{ daily.losses }}L</span>
            </div>
        </div>
        <div class="stat-box">
            <h3>Total All-Time P&L</h3>
            <div class="value {{ 'profit' if total_pnl > 0 else 'loss' if total_pnl < 0 else '' }}">
                ${{ "%.2f"|format(alltime.total_pnl) }}
            </div>
            <p>{{ alltime.total_trades }} total trades</p>
        </div>
        <div class="stat-box">
            <h3>Win Rate</h3>
            <div class="value">{{ "%.1f"|format(win_rate) }}%</div>
            <p>{{ alltime.wins }}W / {{ alltime.losses }}L</p>
        </div>
    </div>

    <h2 style="color:#00d4ff;">Recent Trades</h2>
    <table>
        <tr>
            <th>Time</th>
            <th>Direction</th>
            <th>Entry Price</th>
            <th>Size</th>
            <th>Confidence</th>
            <th>Regime</th>
            <th>P&L</th>
            <th>Status</th>
        </tr>
        {% for trade in trades %}
        <tr>
            <td>{{ trade[1][:19] }}</td>
            <td style="color: {{ '#00ff88' if trade[3] == 'LONG' else '#ff4757' }}">{{ trade[3] }}</td>
            <td>${{ "%.2f"|format(trade[4]) }}</td>
            <td>{{ "%.4f"|format(trade[6]) }}</td>
            <td>{{ "%.1f"|format(trade[9]) }}%</td>
            <td>{{ trade[10] }}</td>
            <td class="{{ 'profit' if trade[7] > 0 else 'loss' if trade[7] < 0 else '' }}">
                ${{ "%.2f"|format(trade[7]) }}
            </td>
            <td class="status-{{ trade[8] }}">{{ trade[8] }}</td>
        </tr>
        {% endfor %}
    </table>

    <div class="refresh">
        Auto-refreshes every 30 seconds
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    daily = dashboard.get_daily_stats()
    alltime = dashboard.get_all_time_stats()
    trades = dashboard.get_recent_trades(20)

    win_rate = 0
    if alltime['total_trades'] > 0:
        win_rate = (alltime['wins'] / alltime['total_trades']) * 100

    return render_template_string(HTML_TEMPLATE,
                                   daily=daily,
                                   alltime=alltime,
                                   trades=trades,
                                   daily_pnl=daily['total_pnl'],
                                   total_pnl=alltime['total_pnl'],
                                   win_rate=win_rate)

if __name__ == '__main__':
    print("=" * 50)
    print("DASHBOARD: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)