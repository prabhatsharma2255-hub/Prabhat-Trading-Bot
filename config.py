"""
Configuration for Delta Exchange AI Trading Bot

ALL VALUES ARE FINALIZED - Do not change unless you know what you're doing
"""

import os

# API Configuration
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "AiFZdExVer9VSEIrBNBZX1djmGHQHZ")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "jjlSbOMqME3vOwjZ7RZamFi8UGM3hmf0M6fsx3D8632a2BISpggy7x5eiaTH")

# Symbol - will be auto-verified on startup
SYMBOL = "BTCUSD"
TRADING_PAIR = "BTCUSD"

# Capital and Risk (PERCENTAGE based)
STARTING_CAPITAL = 100.0

RISK_GRADE_A = 0.03    # 3% per trade for Grade A
RISK_GRADE_B = 0.02    # 2% per trade for Grade B
RISK_GRADE_C = 0.01    # 1% per trade for Grade C

# Leverage Caps
MAX_LEVERAGE_TRENDING = 6
MAX_LEVERAGE_BREAKOUT = 5
MAX_LEVERAGE_RANGING = 3
MAX_LEVERAGE_HIGH_VOL = 2

# Stop Loss
ATR_MULTIPLIER_SL_A = 1.5   # 1.5x ATR for Grade A
ATR_MULTIPLIER_SL_C = 1.2   # 1.2x ATR for Grade C
MAX_SL_DISTANCE_PCT = 0.02   # 2% max SL width

# Take Profit Tiers
TP1_R_MULTIPLE = 1.5        # 1.5x risk
TP2_R_MULTIPLE = 2.5         # 2.5x risk
TP3_R_MULTIPLE = 4.0         # 4.0x risk

TP1_CLOSE_PCT = 0.40         # Close 40% at TP1
TP2_CLOSE_PCT = 0.40         # Close 40% at TP2
TP3_CLOSE_PCT = 0.20         # Close 20% at TP3

# Filters
MIN_SIGNALS_REQUIRED = 4     # out of 5 signals
HTF_CANDLES = 100            # 1h candles to fetch
LTF_CANDLES = 200            # 15m candles to fetch

# Daily Limits
MAX_TRADES_PER_DAY = 5
MAX_DAILY_DRAWDOWN_PCT = 0.06    # 6% max daily drawdown
MAX_CONSECUTIVE_LOSSES = 3
REVIEW_MODE_MIN_TRADES = 20
REVIEW_MODE_MIN_WINRATE = 0.40    # 40% min win rate
REVIEW_MODE_MIN_RR = 1.5          # 1.5 min risk-reward ratio

# Execution
POLLING_INTERVAL = 60             # seconds between cycles
ANTI_CHASE_PCT = 0.003            # 0.3% max slippage allowed
ORDER_TIMEOUT_SECONDS = 30
MAX_OPEN_POSITIONS = 2
CANDLE_CLOSE_WAIT = True          # Wait for candle close before entry

# Timeframes
TIMEFRAMES = {
    "entry": "15m",
    "filter": "1h"
}

# Logging
ENABLE_LOGGING = True
LOG_FILE = "trading_bot.log"

# MODE - SET TO TRUE UNTIL API IS CONFIRMED WORKING
DRY_RUN = True