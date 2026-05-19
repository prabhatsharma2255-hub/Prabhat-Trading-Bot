"""
AI BRAIN - SETUP-BASED TRADING SYSTEM

6 Swing Setups (1-6):
1. SQUEEZE BREAKOUT - Highest leverage (7x)
2. LIQUIDITY SWEEP REVERSAL - Best R:R (6x)
3. BREAK AND RETEST - Structure trade (5x)
4. TREND CONTINUATION PULLBACK - Bread and butter (5x)
5. FIBONACCI GOLDEN RATIO - Precision entry (5x)
6. VWAP MEAN REVERSION - Ranging market (4x)

3 Scalp Setups (7-9):
7. RIBBON MOMENTUM SCALP - Clean trend on 3m (5x)
8. VOLUME BURST CONTINUATION SCALP - Institutional order hit (6x)
9. MICRO BOS SCALP - Structure break (5x)

3 Aggressive Setups (10-12):
10. ROCKET RIDE - Chase the explosive move (6x)
11. NEWS SPIKE TRADE - Pure reaction trade (5x/7x whale)
12. FUNDING RATE SQUEEZE - The crowded trade snap (5x)
"""

import numpy as np
import sqlite3
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import logging
import config

from indicators import MarketState, Indicators

try:
    from news_engine import NewsEngine
except ImportError:
    NewsEngine = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SetupResult:
    """Result of setup scanning"""
    triggered: bool
    setup_name: str
    direction: str
    risk_pct: float
    leverage: int
    stop_loss: float
    tp1: float
    tp2: float
    conditions_met: List[str]
    reason: str


class PatternMemory:
    """Track trade history and learn from it"""

    def __init__(self):
        self.db_file = "trades.db"

    def record_trade(self, setup: str, regime: str, direction: str, pnl: float, outcome: str):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''INSERT INTO pattern_memory
            (timestamp, regime, session, mode, signals_count, direction, pnl, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (datetime.now().isoformat(), regime, "unknown", 0, 0, direction, pnl, outcome))
        conn.commit()
        conn.close()

    def get_setup_win_rate(self, setup: str) -> float:
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("""SELECT COUNT(*), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
            FROM pattern_memory WHERE outcome LIKE ?""", (f"%{setup}%",))
        row = c.fetchone()
        conn.close()
        total = row[0] if row else 0
        wins = row[1] if row and row[1] else 0
        return wins / total if total and total > 15 else 0.5


class AIBrain:
    """Setup-based trading brain"""

    def __init__(self, news_engine=None):
        self.pattern_memory = PatternMemory()
        self.trades_today = 0
        self.consecutive_losses = 0
        self.mode2_consecutive_losses = 0

        self.news_engine = news_engine
        self.trading_suspended = False
        self.suspend_until = 0

        # Setup-specific counters
        self.squeeze_trades_today = 0
        self.rocket_trades_today = 0
        self.news_trades_today = 0
        self.rocket_consecutive_losses = 0
        self.rocket_losses_streak = 0
        self.scalp_trades_today = 0
        self.scalp_consecutive_losses = 0

        self.last_reset_date = datetime.now().date()

    def reset_daily(self):
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.trades_today = 0
            self.consecutive_losses = 0
            self.squeeze_trades_today = 0
            self.rocket_trades_today = 0
            self.news_trades_today = 0
            self.rocket_consecutive_losses = 0
            self.rocket_losses_streak = 0
            self.scalp_trades_today = 0
            self.scalp_consecutive_losses = 0
            self.last_reset_date = today

    def get_session(self) -> Tuple[str, bool]:
        """Get current session and whether trading allowed"""
        utc_hour = datetime.now(timezone.utc).hour

        # Dead session: allow scalping only
        if config.SESSION_DEAD_START <= utc_hour or utc_hour < config.SESSION_DEAD_END:
            return "dead", True  # Allow scalping

        if config.SESSION_ASIA_START <= utc_hour < config.SESSION_LONDON_START:
            return "asia", True
        elif config.SESSION_LONDON_START <= utc_hour < config.SESSION_NY_START:
            return "london", True
        elif config.SESSION_NY_START <= utc_hour < config.SESSION_DEAD_START:
            return "ny", True

        return "ny", True

    def get_session_aggression(self) -> Dict:
        """Get dynamic aggression settings based on session"""
        session, can_trade = self.get_session()

        if session == "dead":
            return {
                "session": session,
                "leverage_mod": -1,
                "confidence_boost": 1,
                "min_conditions": 2,
                "max_daily_multiplier": 0.8,
                "description": "DEAD - scalping allowed"
            }
        elif session == "asia":
            return {
                "session": session,
                "leverage_mod": -1,
                "confidence_boost": 0,
                "min_conditions": 3,
                "max_daily_multiplier": 0.7,
                "description": "ASIA - moderate caution"
            }
        elif session == "london":
            return {
                "session": session,
                "leverage_mod": 0,
                "confidence_boost": 1,
                "min_conditions": 2,
                "max_daily_multiplier": 1.0,
                "description": "LONDON - active trading"
            }
        elif session == "ny":
            return {
                "session": session,
                "leverage_mod": 1,
                "confidence_boost": 2,
                "min_conditions": 2,
                "max_daily_multiplier": 1.0,
                "description": "NY - most aggressive"
            }

        return {
            "session": session,
            "leverage_mod": 0,
            "confidence_boost": 0,
            "min_conditions": 2,
            "max_daily_multiplier": 1.0,
            "description": "default"
        }

    def can_trade(self) -> Tuple[bool, str]:
        """Check daily limits"""
        self.reset_daily()

        if self.trades_today >= config.MAX_TRADES_PER_DAY:
            return False, "max_trades_reached"

        return True, "OK"

    def check_htf_alignment(self, htf_bullish: bool, direction: str) -> Tuple[bool, str]:
        """Check HTF alignment - block only clear conflicts"""
        if not direction or direction == "NONE":
            return False, "no_direction"

        if htf_bullish and direction == "LONG":
            return True, "bull_aligned"
        elif htf_bullish and direction == "SHORT":
            return False, "bull_vs_short_conflict"

        if direction == "LONG":
            return True, "neutral_ok"
        elif direction == "SHORT":
            return True, "neutral_ok"

        return True, "neutral_ok"

    def _compute_scalp_data(self, ltf_candles: List, scalp_1m_candles: List = None, scalp_3m_candles: List = None) -> Dict:
        """FIXED: Compute scalp indicator data from 1m/3m candles for setups 7-9"""
        scalp_data = {}

        # Use 3m candles for ribbon, volume burst, micro structure if available
        # Fall back to 15m candles if scalp candles not provided
        candles_for_scalp = scalp_3m_candles or scalp_1m_candles or ltf_candles

        if candles_for_scalp and len(candles_for_scalp) >= 10:
            indicators_for_scalp = Indicators(candles_for_scalp, min_candles=5)

            if len(candles_for_scalp) >= 21:
                ribbon = indicators_for_scalp.ema_ribbon(candles_for_scalp)
                scalp_data["ribbon_state"] = ribbon.get("ribbon_state", "twisting")
                scalp_data["ribbon_strength"] = ribbon.get("ribbon_strength", "weak")
                scalp_data["ribbon_angle"] = ribbon.get("ribbon_angle", 0)
            else:
                scalp_data["ribbon_state"] = "twisting"
                scalp_data["ribbon_strength"] = "weak"
                scalp_data["ribbon_angle"] = 0

            delta = indicators_for_scalp.momentum_delta(candles_for_scalp)
            scalp_data["delta_bias"] = delta.get("delta_bias", "neutral")
            scalp_data["delta_divergence"] = delta.get("delta_divergence", "none")
            scalp_data["cumulative_delta"] = delta.get("cumulative_delta", 0)

            micro = indicators_for_scalp.micro_structure(candles_for_scalp)
            scalp_data["micro_structure"] = micro.get("micro_structure", "ranging")
            scalp_data["micro_bos"] = micro.get("micro_bos", "none")
            scalp_data["micro_bos_candles_ago"] = micro.get("micro_bos_candles_ago", 999)

            burst = indicators_for_scalp.volume_burst_detector(candles_for_scalp)
            scalp_data["volume_burst"] = burst.get("volume_burst", False)
            scalp_data["burst_direction"] = burst.get("burst_direction", "none")
            scalp_data["burst_quality"] = burst.get("burst_quality", "none")
            scalp_data["burst_candles_ago"] = burst.get("burst_candles_ago", 999)

            rsi_data = indicators_for_scalp.rsi_slope_speed(candles_for_scalp)
            scalp_data["rsi_3m"] = rsi_data.get("rsi_3m", 50)
            scalp_data["rsi_slope"] = rsi_data.get("rsi_slope", 0)
            scalp_data["rsi_state"] = rsi_data.get("rsi_state", "neutral")
        else:
            # Defaults if no candle data available
            scalp_data["ribbon_state"] = "twisting"
            scalp_data["ribbon_strength"] = "weak"
            scalp_data["ribbon_angle"] = 0
            scalp_data["delta_bias"] = "neutral"
            scalp_data["delta_divergence"] = "none"
            scalp_data["cumulative_delta"] = 0
            scalp_data["micro_structure"] = "ranging"
            scalp_data["micro_bos"] = "none"
            scalp_data["micro_bos_candles_ago"] = 999
            scalp_data["volume_burst"] = False
            scalp_data["burst_direction"] = "none"
            scalp_data["burst_quality"] = "none"
            scalp_data["burst_candles_ago"] = 999
            scalp_data["rsi_3m"] = 50
            scalp_data["rsi_slope"] = 0
            scalp_data["rsi_state"] = "neutral"

        return scalp_data

    def _setup_blocked_by_open(self, setup_name: str, open_setups: List[str] = None) -> bool:
        if not open_setups:
            return False
        count = sum(1 for s in open_setups if s == setup_name)
        return count >= config.MAX_SAME_SETUP_TRADES

    def scan_setups(self, state: MarketState, velocity_data: Dict = None,
                 news_engine=None, move_detector=None, ltf_candles: List = None,
                 scalp_data: Dict = None, open_setups: List[str] = None) -> List[SetupResult]:
        """Scan for all 12 setups"""
        results = []

        funding_data = None
        if move_detector:
            funding_data = move_detector.get_market_intelligence()

        # HIGH CONVICTION SWING (1-6)
        result = self._setup_squeeze_breakout(state, ltf_candles, open_setups)
        results.append(result)

        result = self._setup_liquidity_sweep(state, ltf_candles, open_setups)
        results.append(result)

        result = self._setup_break_retest(state, open_setups)
        results.append(result)

        result = self._setup_trend_pullback(state, ltf_candles, open_setups)
        results.append(result)

        result = self._setup_fibonacci(state, open_setups)
        results.append(result)

        result = self._setup_vwap_reversion(state, open_setups)
        results.append(result)

        # SCALPING (7-9)
        result = self._setup_ribbon_scalp(state, scalp_data, open_setups)
        results.append(result)

        result = self._setup_volume_burst_scalp(state, scalp_data, open_setups)
        results.append(result)

        result = self._setup_micro_bos_scalp(state, scalp_data, open_setups)
        results.append(result)

        # AGGRESSIVE (10-12)
        result = self._setup_rocket_ride(state, velocity_data, ltf_candles, scalp_data, open_setups)
        results.append(result)

        result = self._setup_news_spike(state, news_engine, ltf_candles, open_setups)
        results.append(result)

        result = self._setup_funding_squeeze(state, funding_data, open_setups)
        results.append(result)

        return results

    # ============================================================
    # SCALP SETUPS (7-9)
    # ============================================================

    def _setup_ribbon_scalp(self, state: MarketState, scalp_data: Dict = None, open_setups: List[str] = None) -> SetupResult:
        """SETUP 7: RIBBON MOMENTUM SCALP"""
        conditions = []

        if self._setup_blocked_by_open("RIBBON_SCALP", open_setups):
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if self.scalp_trades_today >= 4:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "max_ribbon_reached")

        if state.atr_ratio > 0.015:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "high_volatility")

        session, _ = self.get_session()
        if session not in ["london", "ny"]:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, [], "session_not_allowed")

        # Use scalp_data if provided, otherwise fall back to state defaults
        ribbon_state = scalp_data.get("ribbon_state", "twisting") if scalp_data else state.ribbon_state
        ribbon_strength = scalp_data.get("ribbon_strength", "weak") if scalp_data else state.ribbon_strength
        delta_bias = scalp_data.get("delta_bias", "neutral") if scalp_data else state.delta_bias
        rsi_state = scalp_data.get("rsi_state", "neutral") if scalp_data else state.rsi_state

        if ribbon_state in ["bull", "bear"]:
            conditions.append("ribbon_aligned")

        if ribbon_strength in ["strong", "moderate"]:
            conditions.append("ribbon_strong")

        if (ribbon_state == "bull" and delta_bias == "bull") or (ribbon_state == "bear" and delta_bias == "bear"):
            conditions.append("delta_agrees")

        if (ribbon_state == "bull" and rsi_state == "fast_bull") or (ribbon_state == "bear" and rsi_state == "fast_bear"):
            conditions.append("rsi_fast")

        if state.structure != "ranging":
            if (ribbon_state == "bull" and state.structure == "bullish") or (ribbon_state == "bear" and state.structure == "bearish"):
                conditions.append("structure_agree")
            elif (ribbon_state == "bull" and state.structure == "bearish"):
                return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "structure_opposing")

        if state.rvol > 1.3:
            conditions.append("volume_ok")

        all_met = len(conditions) >= 5

        if all_met:
            direction = "LONG" if ribbon_state == "bull" else "SHORT"
            price = state.current_price

            sl_distance = min(state.atr * 1.5, price * 0.004)
            sl = price - sl_distance if direction == "LONG" else price + sl_distance

            tp = price * 1.006 if direction == "LONG" else price * 0.994

            return SetupResult(True, "RIBBON_SCALP", direction,
                config.SETUP_RIBBON_SCALP_RISK, config.SETUP_RIBBON_SCALP_LEV,
                sl, tp, 0, conditions, "ribbon_momentum")

        return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "no_ribbon")

    def _setup_volume_burst_scalp(self, state: MarketState, scalp_data: Dict = None, open_setups: List[str] = None) -> SetupResult:
        """SETUP 8: VOLUME BURST CONTINUATION SCALP"""
        conditions = []

        if self._setup_blocked_by_open("VOLUME_BURST_SCALP", open_setups):
            return SetupResult(False, "VOLUME_BURST_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if self.scalp_trades_today >= 3:
            return SetupResult(False, "VOLUME_BURST_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "max_burst_reached")

        volume_burst = scalp_data.get("volume_burst", False) if scalp_data else state.volume_burst
        burst_direction = scalp_data.get("burst_direction", "none") if scalp_data else state.burst_direction
        burst_quality = scalp_data.get("burst_quality", "none") if scalp_data else state.burst_quality
        burst_ago = scalp_data.get("burst_candles_ago", 999) if scalp_data else state.burst_candles_ago
        micro_structure = scalp_data.get("micro_structure", "ranging") if scalp_data else state.micro_structure
        ribbon_state = scalp_data.get("ribbon_state", "twisting") if scalp_data else state.ribbon_state
        delta_bias = scalp_data.get("delta_bias", "neutral") if scalp_data else state.delta_bias
        rsi_3m = scalp_data.get("rsi_3m", 50) if scalp_data else state.rsi_3m

        if volume_burst and burst_ago <= 1:
            conditions.append("fresh_burst")

        if burst_quality == "high":
            conditions.append("high_quality_burst")

        if (burst_direction == "bull" and micro_structure == "bullish") or (burst_direction == "bear" and micro_structure == "bearish"):
            conditions.append("micro_agree")

        if ribbon_state in ["bull", "bear", "compressed"]:
            conditions.append("ribbon_ok")

        if (burst_direction == "bull" and delta_bias == "bull") or (burst_direction == "bear" and delta_bias == "bear"):
            conditions.append("delta_agree")

        if not ((burst_direction == "bull" and rsi_3m > 75) or (burst_direction == "bear" and rsi_3m < 25)):
            conditions.append("rsi_not_exhausted")

        all_met = len(conditions) >= 5

        if all_met:
            direction = "LONG" if burst_direction == "bull" else "SHORT"
            price = state.current_price

            sl = price * 0.992 if direction == "LONG" else price * 1.008
            tp = price * 1.008 if direction == "LONG" else price * 0.992

            return SetupResult(True, "VOLUME_BURST_SCALP", direction,
                config.SETUP_VOLUME_BURST_RISK, config.SETUP_VOLUME_BURST_LEV,
                sl, tp, 0, conditions, "volume_burst_continuation")

        return SetupResult(False, "VOLUME_BURST_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "no_burst")

    def _setup_micro_bos_scalp(self, state: MarketState, scalp_data: Dict = None, open_setups: List[str] = None) -> SetupResult:
        """SETUP 9: MICRO BOS SCALP (structure break scalp)"""
        conditions = []

        if self._setup_blocked_by_open("MICRO_BOS_SCALP", open_setups):
            return SetupResult(False, "MICRO_BOS_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if self.scalp_trades_today >= 3:
            return SetupResult(False, "MICRO_BOS_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "max_micro_reached")

        session, _ = self.get_session()
        if session != "ny":
            return SetupResult(False, "MICRO_BOS_SCALP", "NONE", 0, 0, 0, 0, 0, [], "ny_only")

        micro_bos = scalp_data.get("micro_bos", "none") if scalp_data else state.micro_bos
        micro_ago = scalp_data.get("micro_bos_candles_ago", 999) if scalp_data else state.micro_bos_candles_ago
        ribbon_state = scalp_data.get("ribbon_state", "twisting") if scalp_data else state.ribbon_state
        delta_div = scalp_data.get("delta_divergence", "none") if scalp_data else state.delta_divergence
        delta_bias = scalp_data.get("delta_bias", "neutral") if scalp_data else state.delta_bias
        rsi_3m = scalp_data.get("rsi_3m", 50) if scalp_data else state.rsi_3m

        if micro_bos in ["bull", "bear"] and micro_ago <= 2:
            conditions.append("fresh_micro_bos")

        if (micro_bos == "bull" and state.structure == "bullish") or (micro_bos == "bear" and state.structure == "bearish"):
            conditions.append("htf_agree")

        if (micro_bos == "bull" and ribbon_state in ["bull", "twisting"]) or (micro_bos == "bear" and ribbon_state in ["bear", "twisting"]):
            conditions.append("ribbon_ok")

        if (micro_bos == "bull" and (delta_div == "bull" or delta_bias == "bull")) or (micro_bos == "bear" and (delta_div == "bear" or delta_bias == "bear")):
            conditions.append("delta_confirm")

        if state.rvol > 1.5:
            conditions.append("volume_ok")

        if micro_bos == "bull" and 40 <= rsi_3m <= 65:
            conditions.append("rsi_room")
        elif micro_bos == "bear" and 35 <= rsi_3m <= 60:
            conditions.append("rsi_room")

        all_met = len(conditions) >= 5

        if all_met:
            direction = "LONG" if micro_bos == "bull" else "SHORT"
            price = state.current_price

            sl = price * 0.9975 if direction == "LONG" else price * 1.0025
            tp = price * 1.005 if direction == "LONG" else price * 0.995

            return SetupResult(True, "MICRO_BOS_SCALP", direction,
                config.SETUP_MICRO_BOS_RISK, config.SETUP_MICRO_BOS_LEV,
                sl, tp, 0, conditions, "micro_bos_breakout")

        return SetupResult(False, "MICRO_BOS_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "no_micro_bos")

    # ============================================================
    # AGGRESSIVE SETUPS (10-12)
    # ============================================================

    def _setup_rocket_ride(self, state: MarketState, velocity_data: Dict = None,
                       candles: List = None, scalp_data: Dict = None,
                       open_setups: List[str] = None) -> SetupResult:
        """SETUP 10: ROCKET RIDE - Chase the Explosive Move"""
        conditions = []

        if self._setup_blocked_by_open("ROCKET_RIDE", open_setups):
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if not velocity_data:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "no_velocity_data")

        if self.rocket_trades_today >= config.MAX_ROCKET_TRADES:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "max_rocket_reached")

        if self.rocket_losses_streak >= 3:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "rocket_suspended_3losses")

        vel_3m = velocity_data.get("velocity_3m", 0)
        vel_1m = velocity_data.get("velocity_1m", 0)

        if abs(vel_3m) > 0.005:
            momentum_persistent = abs(vel_1m) > 0.003

            candle_expansion = False
            if candles and len(candles) >= 3:
                recent = candles[-3:]
                ranges = [(c.get("high", 0) - c.get("low", 0)) / c.get("close", 1) for c in recent]
                avg_range = sum(ranges) / len(ranges) if ranges else 0
                current_range = ranges[-1] if ranges else 0
                candle_expansion = current_range > avg_range * 1.2

            if momentum_persistent or candle_expansion:
                conditions.append(f"velocity_{vel_3m*100:.1f}%")
            else:
                conditions.append(f"velocity_weak")
        else:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "velocity_below_0.5pct")

        volume_burst = scalp_data.get("volume_burst", False) if scalp_data else getattr(state, 'volume_burst', False)
        burst_quality = scalp_data.get("burst_quality", 'none') if scalp_data else getattr(state, 'burst_quality', 'none')

        if state.rvol < 0.5:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "dead_volume")

        if volume_burst and burst_quality in ["high", "medium"]:
            conditions.append("volume_burst_quality")
        elif state.rvol > 1.0:
            conditions.append("volume_active")
        else:
            conditions.append("volume_weak")

        rsi_val = state.rsi
        if vel_3m > 0 and rsi_val < 78:
            conditions.append("rsi_room_long")
        elif vel_3m < 0 and rsi_val > 22:
            conditions.append("rsi_room_short")
        else:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "rsi_exhausted")

        catalyst = False
        catalyst_reason = ""

        if state.squeeze_fired:
            catalyst = True
            catalyst_reason = "squeeze_fired"
        elif state.last_event in ["BOS_bull", "BOS_bear"] and state.event_candles_ago <= 2:
            catalyst = True
            catalyst_reason = "micro_bos"

        if candles and len(candles) >= 10:
            for c in candles[-10:]:
                if c.get("oi_change", 0) > 0.02:
                    catalyst = True
                    catalyst_reason = "oi_spike"
                    break

        if not catalyst:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "no_catalyst")

        conditions.append(f"catalyst_{catalyst_reason}")

        direction = "LONG" if vel_3m > 0 else "SHORT"
        price = state.current_price

        if candles and len(candles) >= 3:
            recent_lows = [c.get("low", price) for c in candles[-3:]]
            recent_highs = [c.get("high", price) for c in candles[-3:]]

            if direction == "LONG":
                candle_low = min(recent_lows)
                sl_distance = min(price - candle_low, price * 0.005)
                sl = price - sl_distance
            else:
                candle_high = max(recent_highs)
                sl_distance = min(candle_high - price, price * 0.005)
                sl = price + sl_distance
        else:
            sl = price * 0.995 if direction == "LONG" else price * 1.005

        tp = price * 1.008 if direction == "LONG" else price * 0.992

        return SetupResult(True, "ROCKET_RIDE", direction,
            config.SETUP_ROCKET_RISK, config.SETUP_ROCKET_LEV,
            sl, tp, 0, conditions, "rocket_momentum")

    def _setup_news_spike(self, state: MarketState, news_engine=None, candles: List = None,
                      open_setups: List[str] = None) -> SetupResult:
        """SETUP 11: NEWS SPIKE TRADE - Pure Reaction Trade"""
        conditions = []

        if self._setup_blocked_by_open("NEWS_SPIKE", open_setups):
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if self.news_trades_today >= config.MAX_NEWS_TRADES:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "max_news_reached")

        if not news_engine or not news_engine.articles:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "no_news_data")

        now = datetime.now(timezone.utc)

        recent_articles = [a for a in news_engine.articles
                          if (now - a.published_at).total_seconds() < 480]

        if not recent_articles:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "no_recent_news")

        best_article = max(recent_articles, key=lambda x: x.score)
        news_score = best_article.score
        news_age = (now - best_article.published_at).total_seconds() / 60

        is_whale = news_engine.whale_event_bull or news_engine.whale_event_bear
        is_whale_bull = news_engine.whale_event_bull
        is_whale_bear = news_engine.whale_event_bear

        score_threshold = 25 if is_whale else 35
        if abs(news_score) < score_threshold:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, f"score_{news_score}_below_threshold")

        if news_age > 8:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, f"news_age_{news_age:.0f}min")

        conditions.append(f"major_news_{news_score:.0f}")

        if is_whale:
            conditions.append("whale_event")

        if candles and len(candles) >= 5:
            price_5m_ago = candles[-5].get("close", state.current_price)
            price_change = (state.current_price - price_5m_ago) / price_5m_ago

            if news_score > 0 and price_change > 0:
                conditions.append("price_confirming_bull")
            elif news_score < 0 and price_change < 0:
                conditions.append("price_confirming_bear")
            else:
                return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "price_not_confirming")

        if candles and len(candles) >= 5:
            if abs(price_change) > 0.015:
                return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "already_extended_1.5pct")

        conditions.append("not_extended")

        if state.rvol > 2.0:
            conditions.append("volume_real")
        else:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "volume_not_real")

        direction = "LONG" if news_score > 0 else "SHORT"

        if is_whale_bull and direction != "LONG":
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "whale_direction_conflict")
        if is_whale_bear and direction != "SHORT":
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "whale_direction_conflict")

        price = state.current_price
        leverage = 7 if is_whale else 5

        sl = price * 0.994 if direction == "LONG" else price * 1.006

        tp1 = price * 1.01 if direction == "LONG" else price * 0.99
        tp2 = price * 1.018 if direction == "LONG" else price * 0.982

        return SetupResult(True, "NEWS_SPIKE", direction,
            config.SETUP_NEWS_SPIKE_RISK, leverage,
            sl, tp1, tp2, conditions, "news_spike")

    def _setup_funding_squeeze(self, state: MarketState, funding_data: Dict = None,
                            open_setups: List[str] = None) -> SetupResult:
        """SETUP 12: FUNDING RATE SQUEEZE - The Crowded Trade Snap"""
        conditions = []

        if self._setup_blocked_by_open("FUNDING_SQUEEZE", open_setups):
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if not funding_data:
            funding_rate = 0
            funding_bias = "neutral"
            oi_change = 0
        else:
            funding_rate = funding_data.get("funding_rate", 0)
            funding_bias = funding_data.get("funding_bias", "neutral")
            oi_change = funding_data.get("oi_change_pct", 0)

        if funding_rate > 0.0008:
            direction = "SHORT"
            conditions.append("funding_long_crowded")
        elif funding_rate < -0.0008:
            direction = "LONG"
            conditions.append("funding_short_crowded")
        else:
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "funding_not_extreme")

        if oi_change > 0:
            conditions.append("oi_rising")
        else:
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "oi_not_rising")

        if direction == "SHORT":
            if state.structure != "bullish":
                conditions.append("price_against_long_crowd")
            else:
                return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "price_with_crowd")
        else:
            if state.structure != "bearish":
                conditions.append("price_against_short_crowd")
            else:
                return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "price_with_crowd")

        technical_count = 0

        if state.rsi_divergence == "bear_div" and direction == "SHORT":
            conditions.append("rsi_bear_div")
            technical_count += 1
        elif state.rsi_divergence == "bull_div" and direction == "LONG":
            conditions.append("rsi_bull_div")
            technical_count += 1

        if state.liq_sweep_bull and direction == "LONG":
            conditions.append("liq_sweep_agree")
            technical_count += 1
        elif state.liq_sweep_bear and direction == "SHORT":
            conditions.append("liq_sweep_agree")
            technical_count += 1

        if state.macd_state in ["decel_bull", "decel_bear"]:
            if (direction == "LONG" and state.macd_state == "decel_bull") or \
               (direction == "SHORT" and state.macd_state == "decel_bear"):
                conditions.append("macd_decel_agree")
                technical_count += 1

        if technical_count == 0:
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "no_technical_agreement")

        price = state.current_price
        atr = state.atr

        if direction == "SHORT":
            sl = price + atr * 1.5
        else:
            sl = price - atr * 1.5

        risk_distance = abs(price - sl)

        tp1 = price - risk_distance * 1.5 if direction == "SHORT" else price + risk_distance * 1.5
        tp2 = price - risk_distance * 3.0 if direction == "SHORT" else price + risk_distance * 3.0

        return SetupResult(True, "FUNDING_SQUEEZE", direction,
            config.SETUP_FUNDING_SQUEEZE_RISK, config.SETUP_FUNDING_SQUEEZE_LEV,
            sl, tp1, tp2, conditions, "funding_squeeze")

    def _setup_squeeze_breakout(self, state: MarketState, candles: List = None,
                             open_setups: List[str] = None) -> SetupResult:
        """SQUEEZE BREAKOUT - Highest leverage setup"""
        conditions = []

        if self._setup_blocked_by_open("SQUEEZE_BREAKOUT", open_setups):
            return SetupResult(False, "SQUEEZE_BREAKOUT", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.squeeze_fired:
            conditions.append("squeeze_fired")

        if state.rvol > 1.8:
            conditions.append("high_volume")

        if state.squeeze_momentum != "none":
            conditions.append("momentum_confirms")

        if state.rsi_divergence == "hidden_bull":
            conditions.append("bullish_div")

        squeeze_quality = False

        vol_expansion = state.rvol > 1.2

        candle_body_strong = False
        if candles and len(candles) >= 1:
            last = candles[-1]
            body = abs(last.get("close", 0) - last.get("open", 0))
            range_size = last.get("high", 0) - last.get("low", 0)
            if range_size > 0 and (body / range_size) > 0.6:
                candle_body_strong = True

        momentum_accel = state.squeeze_momentum != "none" or state.rsi_divergence != "none"

        squeeze_quality = vol_expansion or candle_body_strong or (momentum_accel and state.rvol > 0.8)

        all_met = (state.squeeze_fired or state.squeeze_on) and squeeze_quality

        if all_met and self.squeeze_trades_today < 1:
            direction = "LONG" if state.squeeze_momentum == "bull" else "SHORT"

            atr = state.atr
            price = state.current_price

            if direction == "LONG":
                sl = price - atr * 1.5
                tp1 = state.fib_target_1 if state.fib_target_1 > 0 else price + atr * 3
                tp2 = state.fib_target_2 if state.fib_target_2 > 0 else price + atr * 5
            else:
                sl = price + atr * 1.5
                tp1 = state.fib_target_1 if state.fib_target_1 > 0 else price - atr * 3
                tp2 = state.fib_target_2 if state.fib_target_2 > 0 else price - atr * 5

            return SetupResult(
                triggered=True,
                setup_name="SQUEEZE_BREAKOUT",
                direction=direction,
                risk_pct=config.SETUP_SQUEEZE_RISK,
                leverage=config.SETUP_SQUEEZE_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="squeeze_breakout"
            )

        return SetupResult(
            triggered=False,
            setup_name="SQUEEZE_BREAKOUT",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="conditions_not_met" if conditions else "no_squeeze"
        )

    def _setup_liquidity_sweep(self, state: MarketState, candles: List = None,
                            open_setups: List[str] = None) -> SetupResult:
        """LIQUIDITY SWEEP REVERSAL"""
        conditions = []

        if self._setup_blocked_by_open("LIQUIDITY_SWEEP", open_setups):
            return SetupResult(False, "LIQUIDITY_SWEEP", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.liq_sweep_bull:
            conditions.append("liq_sweep_bull")
        if state.liq_sweep_bear:
            conditions.append("liq_sweep_bear")

        if state.pattern in ["pin_bull", "bull_engulf"] and state.liq_sweep_bull:
            conditions.append("pattern_confirmation")
        if state.pattern in ["pin_bear", "bear_engulf"] and state.liq_sweep_bear:
            conditions.append("pattern_confirmation")

        if state.rsi < 35 or state.rsi_divergence == "bull_div":
            conditions.append("rsi_confirms")
        if state.rsi > 65 or state.rsi_divergence == "bear_div":
            conditions.append("rsi_confirms")

        if state.obv_div == "bull" and state.liq_sweep_bull:
            conditions.append("obv_div_confirms")
        if state.obv_div == "bear" and state.liq_sweep_bear:
            conditions.append("obv_div_confirms")

        if state.pattern_at_level:
            conditions.append("at_level")

        liq_confirm = False

        if state.liq_sweep_bull:
            if state.pattern in ["pin_bull", "bull_engulf"]:
                liq_confirm = True
            elif state.rsi_divergence == "bull_div" and state.rsi < 60:
                liq_confirm = True
            elif state.macd_state == "accel_bull":
                liq_confirm = True
        elif state.liq_sweep_bear:
            if state.pattern in ["pin_bear", "bear_engulf"]:
                liq_confirm = True
            elif state.rsi_divergence == "bear_div" and state.rsi > 40:
                liq_confirm = True
            elif state.macd_state == "accel_bear":
                liq_confirm = True

        if candles and len(candles) >= 2:
            last_candle = candles[-1]
            prev_candle = candles[-2]

            if state.liq_sweep_bull:
                if last_candle.get("close", 0) > prev_candle.get("close", 0):
                    liq_confirm = True
            elif state.liq_sweep_bear:
                if last_candle.get("close", 0) < prev_candle.get("close", 0):
                    liq_confirm = True

        all_met = (state.liq_sweep_bull or state.liq_sweep_bear) and liq_confirm

        if all_met:
            direction = "LONG" if state.liq_sweep_bull else "SHORT"
            price = state.current_price

            if direction == "LONG":
                sl = state.nearest_liq_below * 0.997 if state.nearest_liq_below > 0 else price * 0.995
                tp1 = price + (price - sl) * 1.5
                tp2 = state.last_swing_high if state.last_swing_high > price else price * 1.03
            else:
                sl = state.nearest_liq_above * 1.003 if state.nearest_liq_above > 0 else price * 1.005
                tp1 = price - (sl - price) * 1.5
                tp2 = state.last_swing_low if state.last_swing_low < price else price * 0.97

            return SetupResult(
                triggered=True,
                setup_name="LIQUIDITY_SWEEP",
                direction=direction,
                risk_pct=config.SETUP_LIQ_SWEEP_RISK,
                leverage=config.SETUP_LIQ_SWEEP_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="liquidity_sweep_reversal"
            )

        return SetupResult(
            triggered=False,
            setup_name="LIQUIDITY_SWEEP",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="no_sweep"
        )

    def _setup_break_retest(self, state: MarketState, open_setups: List[str] = None) -> SetupResult:
        """BREAK AND RETEST"""
        conditions = []

        if self._setup_blocked_by_open("BREAK_RETEST", open_setups):
            return SetupResult(False, "BREAK_RETEST", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.last_event in ["BOS_bull", "BOS_bear"]:
            conditions.append("BOS_fired")
            if state.event_candles_ago < 5:
                conditions.append("recent_BOS")

        if state.rvol > 1.2:
            conditions.append("confirming_volume")

        if state.macd_state not in ["decel_bull", "decel_bear"]:
            conditions.append("macd_ok")

        all_met = state.last_event in ["BOS_bull", "BOS_bear"] and \
                  state.event_candles_ago < 5 and \
                  state.rvol > 1.2

        if all_met:
            direction = "LONG" if state.last_event == "BOS_bull" else "SHORT"
            price = state.current_price
            atr = state.atr

            if direction == "LONG":
                sl = price - atr * 1.2
                tp1 = price + (price - sl) * 2.0
                tp2 = price + (price - sl) * 3.5
            else:
                sl = price + atr * 1.2
                tp1 = price - (sl - price) * 2.0
                tp2 = price - (sl - price) * 3.5

            return SetupResult(
                triggered=True,
                setup_name="BREAK_RETEST",
                direction=direction,
                risk_pct=config.SETUP_BNR_RISK,
                leverage=config.SETUP_BNR_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="break_and_retest"
            )

        return SetupResult(
            triggered=False,
            setup_name="BREAK_RETEST",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="no_recent_BOS"
        )

    def _setup_trend_pullback(self, state: MarketState, candles: List = None,
                           open_setups: List[str] = None) -> SetupResult:
        """TREND CONTINUATION PULLBACK"""
        conditions = []

        if self._setup_blocked_by_open("TREND_PULLBACK", open_setups):
            return SetupResult(False, "TREND_PULLBACK", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.structure in ["bullish", "bearish"]:
            conditions.append("structure_ok")

        if state.rsi_divergence == "hidden_bull" or (state.rsi > 40 and state.rsi < 55):
            conditions.append("rsi_in_zone")

        if state.at_fib and state.which_fib and 0.382 <= state.which_fib <= 0.618:
            conditions.append("fib_pullback")

        if state.vwap_zone in ["fair", "high", "low"]:
            conditions.append("at_vwap")

        if state.macd_state in ["accel_bull", "accel_bear"] or state.macd_fresh_cross:
            conditions.append("macd_confirms")

        if state.htf_bullish and state.structure == "bullish":
            conditions.append("htf_aligned")

        pullback_quality = False

        rsi_reset = 40 < state.rsi < 60
        macd_reexpansion = state.macd_state in ["accel_bull", "accel_bear"]

        rejection_candle = False
        if candles and len(candles) >= 1:
            last = candles[-1]
            body = abs(last.get("close", 0) - last.get("open", 0))
            range_size = last.get("high", 0) - last.get("low", 0)
            upper_wick = last.get("high", 0) - max(last.get("close", 0), last.get("open", 0))
            lower_wick = min(last.get("close", 0), last.get("open", 0)) - last.get("low", 0)

            if range_size > 0:
                if state.structure == "bullish" and lower_wick > body * 0.5:
                    rejection_candle = True
                elif state.structure == "bearish" and upper_wick > body * 0.5:
                    rejection_candle = True

        trend_continuation = state.macd_state in ["accel_bull", "accel_bear", "decel_bull", "decel_bear"]

        pullback_quality = rsi_reset or macd_reexpansion or rejection_candle or trend_continuation

        all_met = state.structure != "ranging" and pullback_quality

        if all_met:
            direction = "LONG" if state.structure == "bullish" else "SHORT"
            price = state.current_price
            atr = state.atr

            if direction == "LONG":
                sl = state.last_swing_low * 0.99 if state.last_swing_low > 0 else price - atr * 1.5
                tp1 = state.last_swing_high if state.last_swing_high > price else price + atr * 2.5
                tp2 = state.fib_target_1 if state.fib_target_1 > 0 else price + atr * 4
            else:
                sl = state.last_swing_high * 1.01 if state.last_swing_high > 0 else price + atr * 1.5
                tp1 = state.last_swing_low if state.last_swing_low < price else price - atr * 2.5
                tp2 = state.fib_target_1 if state.fib_target_1 > 0 else price - atr * 4

            return SetupResult(
                triggered=True,
                setup_name="TREND_PULLBACK",
                direction=direction,
                risk_pct=config.SETUP_PULLBACK_RISK,
                leverage=config.SETUP_PULLBACK_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="trend_continuation"
            )

        return SetupResult(
            triggered=False,
            setup_name="TREND_PULLBACK",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="no_trend_or_pullback"
        )

    def _setup_fibonacci(self, state: MarketState, open_setups: List[str] = None) -> SetupResult:
        """FIBONACCI GOLDEN RATIO"""
        conditions = []

        if self._setup_blocked_by_open("FIBONACCI", open_setups):
            return SetupResult(False, "FIBONACCI", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.at_fib and state.which_fib == 0.618:
            conditions.append("at_618")

        if state.structure != "ranging":
            conditions.append("structure_exists")

        if state.pattern in ["pin_bull", "bull_engulf", "pin_bear", "bear_engulf"]:
            conditions.append("candle_confirms")

        if state.vwap_zone in ["fair", "high", "low"]:
            conditions.append("vwap_ok")

        all_met = state.at_fib and state.which_fib == 0.618 and \
                  state.pattern in ["pin_bull", "bull_engulf", "pin_bear", "bear_engulf"] and \
                  state.structure != "ranging"

        if all_met:
            direction = "LONG" if state.fib_dir == "from_low" else "SHORT"
            price = state.current_price

            fib_levels = state.fib_levels or {}

            if direction == "LONG":
                sl = fib_levels.get(0.786, price * 0.99)
                tp1 = state.fib_target_1
                tp2 = state.fib_target_2
            else:
                sl = fib_levels.get(0.786, price * 1.01)
                tp1 = state.fib_target_1
                tp2 = state.fib_target_2

            return SetupResult(
                triggered=True,
                setup_name="FIBONACCI",
                direction=direction,
                risk_pct=config.SETUP_FIBONACCI_RISK,
                leverage=config.SETUP_FIBONACCI_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="fibonacci_618"
            )

        return SetupResult(
            triggered=False,
            setup_name="FIBONACCI",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="not_at_618"
        )

    def _setup_vwap_reversion(self, state: MarketState, open_setups: List[str] = None) -> SetupResult:
        """VWAP MEAN REVERSION"""
        conditions = []

        if self._setup_blocked_by_open("VWAP_REVERSION", open_setups):
            return SetupResult(False, "VWAP_REVERSION", "NONE", 0, 0, 0, 0, 0, conditions, "already_open")

        if state.vwap_zone in ["extreme_high", "extreme_low"]:
            conditions.append("at_extreme")

        if state.rsi > 72 or state.rsi < 28:
            conditions.append("rsi_extreme")

        if state.stoch_k > 85 or state.stoch_k < 15:
            conditions.append("stoch_extreme")

        if state.macd_state in ["decel_bull", "decel_bear"]:
            conditions.append("momentum_fading")

        if state.pattern in ["pin_bull", "pin_bear"]:
            conditions.append("pattern_confirms")

        if state.vwap_zone != "fair":
            conditions.append("not_fair_value")

        all_met = state.vwap_zone in ["extreme_high", "extreme_low"] and \
                  (state.rsi > 72 or state.rsi < 28) and \
                  (state.stoch_k > 85 or state.stoch_k < 15)

        session, can_trade = self.get_session()
        if session == "asia" or session == "dead":
            return SetupResult(
                triggered=False,
                setup_name="VWAP_REVERSION",
                direction="NONE",
                risk_pct=0,
                leverage=0,
                stop_loss=0,
                tp1=0,
                tp2=0,
                conditions_met=conditions,
                reason="session_not_allowed"
            )

        if all_met:
            direction = "SHORT" if state.vwap_zone == "extreme_high" else "LONG"
            price = state.current_price

            if direction == "LONG":
                sl = state.vwap_lower_2 * 0.995
                tp1 = state.vwap_lower_1
                tp2 = state.vwap
            else:
                sl = state.vwap_upper_2 * 1.005
                tp1 = state.vwap_upper_1
                tp2 = state.vwap

            return SetupResult(
                triggered=True,
                setup_name="VWAP_REVERSION",
                direction=direction,
                risk_pct=config.SETUP_VWAP_REVERT_RISK,
                leverage=config.SETUP_VWAP_REVERT_LEV,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                conditions_met=conditions,
                reason="vwap_mean_reversion"
            )

        return SetupResult(
            triggered=False,
            setup_name="VWAP_REVERSION",
            direction="NONE",
            risk_pct=0,
            leverage=0,
            stop_loss=0,
            tp1=0,
            tp2=0,
            conditions_met=conditions,
            reason="not_at_extreme"
        )

    def analyze(self, ltf_candles: List[Dict], htf_candles: Optional[List[Dict]] = None,
            velocity_data: Dict = None, news_engine=None, move_detector=None,
            scalp_1m_candles: List[Dict] = None, scalp_3m_candles: List[Dict] = None,
            open_setups: List[str] = None) -> Dict:
        """Main analysis - run all indicators, score all setups, pick best"""
        indicators = Indicators(ltf_candles)
        state = indicators.get_all_indicators(htf_candles)

        session, can_trade_session = self.get_session()

        can_trade, reason = self.can_trade()

        scalp_data = self._compute_scalp_data(ltf_candles, scalp_1m_candles, scalp_3m_candles)

        setups = self.scan_setups(state, velocity_data, news_engine, move_detector, ltf_candles, scalp_data, open_setups)

        # Score all triggered setups, pick the best by confidence
        triggered_setup = None
        best_score = 0
        scored = []

        if can_trade and can_trade_session:
            for result in setups:
                if not result.triggered:
                    continue

                score = self._score_setup(result, state)

                if score > best_score:
                    best_score = score
                    triggered_setup = result
                    scored.append((result.setup_name, score))

            if scored and len(scored) > 1:
                names = ", ".join(f"{n}({s})" for n, s in scored)
                logger.info(f"CONFIDENCE SCORES: {names} | Winner: {triggered_setup.setup_name} ({best_score})")

        if triggered_setup:
            self.trades_today += 1
            if triggered_setup.setup_name == "SQUEEZE_BREAKOUT":
                self.squeeze_trades_today += 1
            elif triggered_setup.setup_name == "ROCKET_RIDE":
                self.rocket_trades_today += 1
            elif triggered_setup.setup_name == "NEWS_SPIKE":
                self.news_trades_today += 1

        session_aggression = self.get_session_aggression()

        return {
            "can_trade": triggered_setup is not None,
            "state": state,
            "session": session,
            "session_aggression": session_aggression,
            "setup": triggered_setup,
            "skip_reason": reason if not triggered_setup else None,
            "all_setups": setups
        }

    def _score_setup(self, setup: SetupResult, state: MarketState) -> int:
        """Confidence score for a triggered setup. Higher = better."""
        score = len(setup.conditions_met) * 10

        if state.htf_bullish and setup.direction == "LONG":
            score += 20
        elif not state.htf_bullish and setup.direction == "SHORT":
            score += 20

        if state.vwap_event == "reclaim" and setup.direction == "LONG":
            score += 15
        elif state.vwap_event == "rejection" and setup.direction == "SHORT":
            score += 15

        if state.squeeze_fired:
            score += 10

        if state.rvol > 1.5:
            score += 5
        elif state.rvol < 0.5:
            score -= 10

        if state.atr_ratio < 0.02:
            score += 5

        if state.pattern in ["pin_bull", "pin_bear", "bull_engulf", "bear_engulf"]:
            score += 10

        if state.structure != "ranging":
            score += 5

        return max(score, 0)
