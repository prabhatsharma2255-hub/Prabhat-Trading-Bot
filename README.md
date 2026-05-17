# Delta Exchange AI Trading Bot

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export DELTA_API_KEY="your_api_key"
export DELTA_API_SECRET="your_api_secret"
```

3. Run:
```bash
python main.py
```

## Configuration

Edit `config.py` to adjust:
- CAPITAL: Starting capital ($100)
- RISK_PER_TRADE: Max risk per trade (5%)
- DRY_RUN: Set to False for live trading
- POLLING_INTERVAL: Seconds between analysis (60s)

## Features

- 13 technical indicators (RSI, MACD, Bollinger, EMA, ATR, etc.)
- AI confidence engine with dynamic weighting
- Automatic market regime detection (trending/ranging/volatile)
- Dynamic position sizing and leverage
- Stop loss and take profit automation
- Risk management (max daily loss, max trades/day)
- Full logging

## Disclaimer

⚠️ Trading futures carries high risk. This bot is for educational purposes. Start with DRY_RUN=True and test thoroughly before using real money.