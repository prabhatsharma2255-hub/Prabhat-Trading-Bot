"""
Configuration for Delta Exchange AI Trading Bot

DUAL TRADE MODES:
- Mode 1: Conviction Trade (4-5/5 signals, full size)
- Mode 2: Calculated Risk Trade (3/5 signals + price action, smaller size)
"""

import os

# API Configuration
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "AiFZdExVer9VSEIrBNBZX1djmGHQHZ")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "jjlSbOMqME3vOwjZ7RZamFi8UGM3hmf0M6fsx3D8632a2BISpggy7x5eiaTH")

# Symbol - will be auto-verified on startup
SYMBOL = "BTCUSD"
TRADING_PAIR = "BTCUSD"

# Capital
STARTING_CAPITAL = 100.0

# ============================================================
# TRADE MODE SETTINGS
# ============================================================

# Mode 1: Conviction Trade (sniper shot - high confidence)
MIN_SIGNALS_MODE1 = 4       # 4-5/5 signals required

# Mode 2: Calculated Risk Trade (more opportunities)
MIN_SIGNALS_MODE2 = 3       # 3/5 signals required
REQUIRE_PRICE_ACTION = True # Mode 2 must have price action signal

# ============================================================
# SIZING (Percentage of account)
# ============================================================

# Mode 1 Sizing
RISK_MODE1_GRADE_A = 0.03   # 3% - full conviction
RISK_MODE1_GRADE_B = 0.02   # 2% - good conviction
RISK_MODE1_GRADE_C = 0.01   # 1% - lower conviction

# Mode 2 Sizing
RISK_MODE2_DEFAULT = 0.015  # 1.5% - standard risk mode
RISK_MODE2_REDUCED = 0.01   # 1% - after 2 consecutive losses
RISK_MODE2_BOOSTED = 0.02   # 2% - pattern memory says edge found

# ============================================================
# LEVERAGE
# ============================================================

MAX_LEV_MODE1_TREND = 6            # Mode 1 in trending
MAX_LEV_MODE1_BREAKOUT = 7          # Mode 1 breakout (high conviction)
MAX_LEV_MODE1_HIGH_VOL = 4          # Mode 1 high volatility
MAX_LEV_MODE2 = 4                   # Mode 2 max leverage
MAX_LEV_HIGH_VOL = 4                # High volatility cap

# ============================================================
# STOP LOSS
# ============================================================

ATR_MULTIPLIER_MODE1 = 1.5   # 1.5x ATR for Mode 1
ATR_MULTIPLIER_MODE2 = 1.2   # 1.2x ATR for Mode 2 (tighter)
MAX_SL_DISTANCE_PCT = 0.02   # 2% max SL width

# ============================================================
# TAKE PROFIT - MODE 1 (Multiple of risk)
# ============================================================

TP1_R_MODE1 = 1.5   # Close 40% at 1.5R
TP2_R_MODE1 = 2.5   # Close 40% at 2.5R
TP3_R_MODE1 = 4.0   # Close 20% at 4.0R

TP1_CLOSE_PCT = 0.40
TP2_CLOSE_PCT = 0.40
TP3_CLOSE_PCT = 0.20

# ============================================================
# TAKE PROFIT - MODE 2 (Tighter - exit faster)
# ============================================================

TP1_R_MODE2 = 1.2   # Close 50% at 1.2R
TP2_R_MODE2 = 2.0   # Close 50% at 2.0R
# NO TP3 for Mode 2 - exit fully at TP2

TP1_CLOSE_PCT_MODE2 = 0.50
TP2_CLOSE_PCT_MODE2 = 0.50

# ============================================================
# DAILY LIMITS
# ============================================================

MAX_TRADES_DAY = 8           # Total max trades per day
MAX_MODE1_TRADES_DAY = 3     # Max conviction trades
MAX_MODE2_TRADES_DAY = 5     # Max risk trades
MAX_DAILY_DD_PCT = 0.07      # 7% max daily drawdown

MODE2_SUSPEND_CONSEC_LOSSES = 3  # Suspend Mode 2 after 3 losses
MAX_CONSECUTIVE_LOSSES = 3       # Pause after 3 consecutive losses

# ============================================================
# PATTERN MEMORY (Own Brain)
# ============================================================

PATTERN_MEMORY_MIN_SAMPLES = 10    # Min trades before using pattern data
PATTERN_MEMORY_BOOST_THRESHOLD = 0.55   # Win rate > 55% = boost size
PATTERN_MEMORY_REDUCE_THRESHOLD = 0.35  # Win rate < 35% = skip Mode 2
LEARNING_MODE_TRADES = 20              # First 20 trades = learning mode

# ============================================================
# FILTERS
# ============================================================

HTF_CANDLES = 100            # 1h candles to fetch
LTF_CANDLES = 200            # 15m candles to fetch
MIN_VOLUME_RATIO_MODE2 = 1.3 # Mode 2 requires >1.3x avg volume

# ============================================================
# EXECUTION
# ============================================================

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

# MODE - SET TO TRUE FOR DRY RUN, FALSE FOR LIVE
DRY_RUN = False