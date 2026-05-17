# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os

DELTA_API_KEY = "AiFZdExVer9VSEIrBNBZX1djmGHQHZ"
DELTA_API_SECRET = "jjlSbOMqME3vOwjZ7RZamFi8UGM3hmf0M6fsx3D8632a2BISpggy7x5eiaTH"

SYMBOL = "BTCUSD"
TRADING_PAIR = "BTCUSD"

CAPITAL = 100.0
RISK_PER_TRADE = 0.05
MAX_RISK_AMOUNT = 5.0

TIMEFRAMES = {
    "scalp": "5m",
    "primary": "15m",
    "trend": "1h"
}

MAX_LEVERAGE = 8
MIN_LEVERAGE = 3

CONFIDENCE_THRESHOLDS = {
    "strong_sell": 30,
    "weak_sell": 45,
    "neutral": 55,
    "weak_buy": 70,
    "strong_buy": 85
}

ATR_MULTIPLIER_SL = 2.0
ATR_MULTIPLIER_TP = 3.0

ENABLE_LOGGING = True
LOG_FILE = "trading_bot.log"

DRY_RUN = False

POLLING_INTERVAL = 60