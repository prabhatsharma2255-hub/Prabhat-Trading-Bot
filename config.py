"""
Delta Exchange Trading Bot - Complete System
12 SETUPS: 6 swing + 3 scalp + 3 aggressive
"""

import os

# API Configuration
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "AiFZdExVer9VSEIrBNBZX1djmGHQHZ")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "jjlSbOMqME3vOwjZ7RZamFi8UGM3hmf0M6fsx3D8632a2BISpggy7x5eiaTH")

# Symbol
SYMBOL = "BTCUSD"

# Account
STARTING_CAPITAL = 100.0
DRY_RUN = False  # LIVE TRADING ENABLED
MIN_POSITION_USD = 10.0  # Minimum $10 position to execute

# ============================================================
# SETUP RISKS AND LEVERAGE
# ============================================================

# Swing Setups (1-6, 12)
SETUP_SQUEEZE_RISK = 0.030      # 3%
SETUP_SQUEEZE_LEV = 7
SETUP_LIQ_SWEEP_RISK = 0.025    # 2.5%
SETUP_LIQ_SWEEP_LEV = 6
SETUP_BNR_RISK = 0.025          # 2.5%
SETUP_BNR_LEV = 5
SETUP_PULLBACK_RISK = 0.025     # 2.5%
SETUP_PULLBACK_LEV = 5
SETUP_FIBONACCI_RISK = 0.020     # 2%
SETUP_FIBONACCI_LEV = 5
SETUP_VWAP_REVERT_RISK = 0.020   # 2%
SETUP_VWAP_REVERT_LEV = 4
SETUP_FUNDING_SQUEEZE_RISK = 0.025  # 2.5%
SETUP_FUNDING_SQUEEZE_LEV = 5

# Scalp Setups (7-9)
SETUP_RIBBON_SCALP_RISK = 0.015   # 1.5%
SETUP_RIBBON_SCALP_LEV = 5
SETUP_VOLUME_BURST_RISK = 0.020   # 2%
SETUP_VOLUME_BURST_LEV = 6
SETUP_MICRO_BOS_RISK = 0.015       # 1.5%
SETUP_MICRO_BOS_LEV = 5

# Aggressive Setups (10-12)
SETUP_ROCKET_RISK = 0.015          # 1.5%
SETUP_ROCKET_LEV = 6
SETUP_NEWS_SPIKE_RISK = 0.020      # 2%
SETUP_NEWS_SPIKE_LEV = 5
SETUP_NEWS_WHALE_LEV = 7           # 7x for whale events

# ============================================================
# INDICATOR PARAMETERS
# ============================================================

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ADX_PERIOD = 14
ATR_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
KC_PERIOD = 20
KC_MULT = 1.5
SWING_LOOKBACK = 3
FIB_MIN_RANGE_PCT = 0.02
EQUAL_LEVEL_TOLERANCE = 0.002
LTF_CANDLES = 200
HTF_CANDLES = 100

# Scalp-specific
SCALP_3M_CANDLES = 150
SCALP_1M_CANDLES = 100
SCALP_RSI_PERIOD = 7
SCALP_EMA_PERIODS = [5, 8, 13, 21]

# ============================================================
# DAILY LIMITS (COMBINED 12 SETUPS)
# ============================================================

MAX_TOTAL_TRADES_DAY = 12
MAX_TRADES_PER_DAY = 12
MAX_SWING_TRADES = 5       # setups 1-6, 12
MAX_SCALP_TRADES = 7       # setups 7-9
MAX_ROCKET_TRADES = 4     # setup 10
MAX_NEWS_TRADES = 3       # setup 11
MAX_OPEN_POSITIONS = 3
MAX_DAILY_DD_PCT = 0.08    # 8%
MAX_DAILY_RISK_TOTAL = 0.12

# Aggressive Setup Guards
ROCKET_SUSPEND_LOSSES = 3
ROCKET_REENTRY_ALLOWED = 1
NEWS_SPIKE_TIME_LIMIT_MIN = 20
FUNDING_TIME_LIMIT_HRS = 4
FORCE_SCALP_CLOSE_MIN = 25

# ============================================================
# VELOCITY & EXPLOSION THRESHOLDS
# ============================================================

VELOCITY_1M_THRESHOLD = 0.004   # 0.4%
VELOCITY_3M_THRESHOLD = 0.008   # 0.8%
VELOCITY_5M_THRESHOLD = 0.015   # 1.5%
VOLUME_EXPLOSION_MULT = 5.0
FUNDING_CROWDED_THRESHOLD = 0.0008  # 0.08%
FUNDING_NORMAL_THRESHOLD = 0.0003   # 0.03%

# ============================================================
# NEWS API CONFIG
# ============================================================

CRYPTOPANIC_TOKEN = "your_free_token_here"
NEWS_POLL_INTERVAL_MIN = 5
FNG_POLL_INTERVAL_MIN = 60
COINGECKO_POLL_MIN = 15
RSS_POLL_INTERVAL_MIN = 3
MEMPOOL_POLL_MIN = 10
FUNDING_POLL_MIN = 10
OI_POLL_MIN = 5

SENTIMENT_BOOST_THRESHOLD = 20
SENTIMENT_BLOCK_LONG = -50
SENTIMENT_BLOCK_SHORT = 50
FNG_EXTREME_FEAR = 15
FNG_EXTREME_GREED = 85
WHALE_EVENT_EXPIRY_HRS = 4
BLACK_SWAN_SUSPEND_HRS = 4
BLACK_SWAN_REDUCED_SIZE_HRS = 24

NEWS_FULL_WEIGHT_MIN = 15
NEWS_DECAY_1HR = 0.7
NEWS_DECAY_4HR = 0.4
NEWS_EXPIRED_HRS = 4

# ============================================================
# MOVE DETECTOR CONFIG
# ============================================================

MOVE_DETECTOR_INTERVAL_SEC = 30
MICRO_SURGE_PCT = 0.4
EXPLOSIVE_MOVE_PCT = 1.5

# ============================================================
# SESSIONS (UTC)
# ============================================================

SESSION_ASIA_START = 2
SESSION_LONDON_START = 7
SESSION_NY_START = 13
SESSION_DEAD_START = 22
SESSION_DEAD_END = 2

# ============================================================
# EXECUTION
# ============================================================

POLLING_INTERVAL = 60
TIMEFRAMES = {
    "entry": "15m",
    "filter": "1h",
    "scalp_3m": "3m",
    "scalp_1m": "1m"
}

LOG_FILE = "trading_bot.log"
ENABLE_LOGGING = True