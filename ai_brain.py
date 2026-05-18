"""
AI BRAIN - SETUP-BASED TRADING SYSTEM

6 Named Setups:
1. SQUEEZE BREAKOUT - Highest leverage (7x)
2. LIQUIDITY SWEEP REVERSAL - Best R:R (6x)
3. TREND CONTINUATION PULLBACK - Bread and butter (5x)
4. VWAP MEAN REVERSION - Ranging market (4x)
5. BREAK AND RETEST - Structure trade (5x)
6. FIBONACCI GOLDEN RATIO - Precision entry (5x)

Each setup is a complete trade thesis with:
- Required conditions
- Direction
- Position sizing
- Stop loss
- Take profit targets
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
        total, wins = c.fetchone()
        conn.close()
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
        
        if config.SESSION_DEAD_START <= utc_hour or utc_hour < config.SESSION_DEAD_END:
            return "dead", False
        
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
                "leverage_mod": -2,
                "confidence_boost": 0,
                "min_conditions": 4,
                "max_daily_multiplier": 0.5,
                "description": "DEAD - reduce aggression"
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
    
    def scan_setups(self, state: MarketState, velocity_data: Dict = None, 
                 news_engine=None, move_detector=None, ltf_candles: List = None) -> List[SetupResult]:
        """Scan for all 12 setups in priority order"""
        results = []
        
        funding_data = None
        if move_detector:
            funding_data = move_detector.get_market_intelligence()
        
        # HIGH CONVICTION SWING (1-6)
        result = self._setup_squeeze_breakout(state, ltf_candles)
        results.append(result)
        
        result = self._setup_liquidity_sweep(state, ltf_candles)
        results.append(result)
        
        result = self._setup_break_retest(state)
        results.append(result)
        
        result = self._setup_trend_pullback(state, ltf_candles)
        results.append(result)
        
        result = self._setup_fibonacci(state)
        results.append(result)
        
        result = self._setup_vwap_reversion(state)
        results.append(result)
        
        # SCALPING (7-9)
        result = self._setup_ribbon_scalp(state)
        results.append(result)
        
        result = self._setup_volume_burst_scalp(state)
        results.append(result)
        
        result = self._setup_micro_bos_scalp(state)
        results.append(result)
        
        # AGGRESSIVE (10-12) - Check these for explosive moves
        # SETUP 10: ROCKET RIDE - priority after news
        result = self._setup_rocket_ride(state, velocity_data, ltf_candles, None)
        results.append(result)
        
        # SETUP 11: NEWS SPIKE - highest priority for reactive trading
        result = self._setup_news_spike(state, news_engine, ltf_candles)
        results.append(result)
        
        # SETUP 12: FUNDING SQUEEZE - contrarian setup
        result = self._setup_funding_squeeze(state, funding_data)
        results.append(result)
        
        return results
    
    # ============================================================
    # SCALP SETUPS (7-9)
    # ============================================================
    
    def _setup_ribbon_scalp(self, state: MarketState, scalp_data: Dict = None) -> SetupResult:
        """SETUP 7: RIBBON MOMENTUM SCALP
        When: Clean trend on 3m, momentum burst confirmation
        Required: ribbon aligned, delta matches, rsi fast, volume, london/ny session
        """
        conditions = []
        
        if self.scalp_trades_today >= 3:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "max_ribbon_reached")
        
        if state.atr_ratio > 0.015:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, conditions, "high_volatility")
        
        session, _ = self.get_session()
        if session not in ["london", "ny"]:
            return SetupResult(False, "RIBBON_SCALP", "NONE", 0, 0, 0, 0, 0, [], "session_not_allowed")
        
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
    
    def _setup_volume_burst_scalp(self, state: MarketState, scalp_data: Dict = None) -> SetupResult:
        """SETUP 8: VOLUME BURST CONTINUATION SCALP
        When: Institutional order hits, ride the aftershock
        Required: burst on last candle, high quality, micro structure agrees
        """
        conditions = []
        
        if self.scalp_trades_today >= 2:
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
    
    def _setup_micro_bos_scalp(self, state: MarketState, scalp_data: Dict = None) -> SetupResult:
        """SETUP 9: MICRO BOS SCALP (structure break scalp)
        When: 1m structure breaks with confirmation, NY session only
        Required: micro_bos recent, 15m agrees, ribbon matches, delta confirms
        """
        conditions = []
        
        if self.scalp_trades_today >= 2:
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
        
        if micro_bos == "bull" and ribbon_state in ["bull", "twisting"] or micro_bos == "bear" and ribbon_state in ["bear", "twisting"]:
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
                       candles: List = None, scalp_data: Dict = None) -> SetupResult:
        """SETUP 10: ROCKET RIDE - Chase the Explosive Move
        Trigger: velocity_3min > 1.0%, volume burst high quality, RSI not exhausted, catalyst present
        Params: 6x lev, 1.5% risk, 0.5% max SL, 0.8% TP, 10min time exit
        Max: 4/day, suspend after 3 losses
        """
        conditions = []
        
        if not velocity_data:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "no_velocity_data")
        
        if self.rocket_trades_today >= config.MAX_ROCKET_TRADES:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "max_rocket_reached")
        
        if self.rocket_losses_streak >= 3:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "rocket_suspended_3losses")
        
        vel_3m = velocity_data.get("velocity_3m", 0)
        vel_1m = velocity_data.get("velocity_1m", 0)
        
        # CONDITION 1: Velocity > 0.5% WITH momentum persistence OR candle expansion
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
        
        # CONDITION 2: Adaptive volume - reject dead, allow medium+
        volume_burst = getattr(state, 'volume_burst', False)
        burst_quality = getattr(state, 'burst_quality', 'none')
        
        if state.rvol < 0.5:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "dead_volume")
        
        if volume_burst and burst_quality in ["high", "medium"]:
            conditions.append("volume_burst_quality")
        elif state.rvol > 1.0:
            conditions.append("volume_active")
        else:
            conditions.append("volume_weak")
        
        # CONDITION 3: RSI not exhausted
        rsi_val = state.rsi
        if vel_3m > 0 and rsi_val < 78:
            conditions.append("rsi_room_long")
        elif vel_3m < 0 and rsi_val > 22:
            conditions.append("rsi_room_short")
        else:
            return SetupResult(False, "ROCKET_RIDE", "NONE", 0, 0, 0, 0, 0, conditions, "rsi_exhausted")
        
        # CONDITION 4: News or Technical Catalyst
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
        
        # All 4 conditions met - execute
        direction = "LONG" if vel_3m > 0 else "SHORT"
        price = state.current_price
        
        # SL: low/high of last 3 candles, HARD LIMIT 0.5% max
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
        
        # TP: 0.8% fixed
        tp = price * 1.008 if direction == "LONG" else price * 0.992
        
        return SetupResult(True, "ROCKET_RIDE", direction,
            config.SETUP_ROCKET_RISK, config.SETUP_ROCKET_LEV,
            sl, tp, 0, conditions, "rocket_momentum")
    
    def _setup_news_spike(self, state: MarketState, news_engine=None, candles: List = None) -> SetupResult:
        """SETUP 11: NEWS SPIKE TRADE - Pure Reaction Trade
        Trigger: major news (>35 score, <8min), price confirming, not extended, volume real
        Whale: score >25, 7x leverage
        Params: 5x lev (7x whale), 2% risk, 0.6% SL, TP1 1.0% (60%), TP2 1.8% (40%)
        Max: 3/day, 20min time exit
        """
        conditions = []
        
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
        
        # CONDITION 1: Major News Event
        score_threshold = 25 if is_whale else 35
        if abs(news_score) < score_threshold:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, f"score_{news_score}_below_threshold")
        
        if news_age > 8:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, f"news_age_{news_age:.0f}min")
        
        conditions.append(f"major_news_{news_score:.0f}")
        
        if is_whale:
            conditions.append("whale_event")
        
        # CONDITION 2: Price Confirming News
        if candles and len(candles) >= 5:
            price_5m_ago = candles[-5].get("close", state.current_price)
            price_change = (state.current_price - price_5m_ago) / price_5m_ago
            
            if news_score > 0 and price_change > 0:
                conditions.append("price_confirming_bull")
            elif news_score < 0 and price_change < 0:
                conditions.append("price_confirming_bear")
            else:
                return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "price_not_confirming")
        
        # CONDITION 3: Not Already Extended
        if candles and len(candles) >= 5:
            if abs(price_change) > 0.015:
                return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "already_extended_1.5pct")
        
        conditions.append("not_extended")
        
        # CONDITION 4: Volume Real
        if state.rvol > 2.0:
            conditions.append("volume_real")
        else:
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "volume_not_real")
        
        # Execute - all conditions met
        direction = "LONG" if news_score > 0 else "SHORT"
        
        # For whale events, check direction alignment
        if is_whale_bull and direction != "LONG":
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "whale_direction_conflict")
        if is_whale_bear and direction != "SHORT":
            return SetupResult(False, "NEWS_SPIKE", "NONE", 0, 0, 0, 0, 0, conditions, "whale_direction_conflict")
        
        price = state.current_price
        leverage = 7 if is_whale else 5
        
        # SL: 0.6% from entry
        sl = price * 0.994 if direction == "LONG" else price * 1.006
        
        # TP1: 1.0% (60%), TP2: 1.8% (40%)
        tp1 = price * 1.01 if direction == "LONG" else price * 0.99
        tp2 = price * 1.018 if direction == "LONG" else price * 0.982
        
        return SetupResult(True, "NEWS_SPIKE", direction,
            config.SETUP_NEWS_SPIKE_RISK, leverage,
            sl, tp1, tp2, conditions, "news_spike")
    
    def _setup_funding_squeeze(self, state: MarketState, funding_data: Dict = None) -> SetupResult:
        """SETUP 12: FUNDING RATE SQUEEZE - The Crowded Trade Snap
        Trigger: extreme funding (>0.08% or <-0.08%), OI rising, price against crowd, technical agree
        Params: 5x lev, 2.5% risk, TP1 1.5R (40%), TP2 3.0R (40%), TP3 on funding normalize
        Max: 2/day, 4hr time exit
        """
        conditions = []
        
        if not funding_data:
            funding_rate = 0
            funding_bias = "neutral"
            oi_change = 0
        else:
            funding_rate = funding_data.get("funding_rate", 0)
            funding_bias = funding_data.get("funding_bias", "neutral")
            oi_change = funding_data.get("oi_change_pct", 0)
        
        # CONDITION 1: Extreme Funding
        if funding_rate > 0.0008:
            direction = "SHORT"
            conditions.append("funding_long_crowded")
        elif funding_rate < -0.0008:
            direction = "LONG"
            conditions.append("funding_short_crowded")
        else:
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "funding_not_extreme")
        
        # CONDITION 2: OI Confirming Crowding
        if oi_change > 0:
            conditions.append("oi_rising")
        else:
            return SetupResult(False, "FUNDING_SQUEEZE", "NONE", 0, 0, 0, 0, 0, conditions, "oi_not_rising")
        
        # CONDITION 3: Price Against Crowd
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
        
        # CONDITION 4: Technical Agreement
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
        
        # All conditions met - execute
        price = state.current_price
        atr = state.atr
        
        # SL: above/below last swing high/low
        if direction == "SHORT":
            sl = price + atr * 1.5
        else:
            sl = price - atr * 1.5
        
        risk_distance = abs(price - sl)
        
        # TP1: 1.5R (40%), TP2: 3.0R (40%)
        tp1 = price - risk_distance * 1.5 if direction == "SHORT" else price + risk_distance * 1.5
        tp2 = price - risk_distance * 3.0 if direction == "SHORT" else price + risk_distance * 3.0
        
        return SetupResult(True, "FUNDING_SQUEEZE", direction,
            config.SETUP_FUNDING_SQUEEZE_RISK, config.SETUP_FUNDING_SQUEEZE_LEV,
            sl, tp1, tp2, conditions, "funding_squeeze")
    
    def _setup_squeeze_breakout(self, state: MarketState, candles: List = None) -> SetupResult:
        """SQUEEZE BREAKOUT - Highest leverage setup"""
        conditions = []
        
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
    
    def _setup_liquidity_sweep(self, state: MarketState, candles: List = None) -> SetupResult:
        """LIQUIDITY SWEEP REVERSAL"""
        conditions = []
        
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
    
    def _setup_break_retest(self, state: MarketState) -> SetupResult:
        """BREAK AND RETEST"""
        conditions = []
        
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
    
    def _setup_trend_pullback(self, state: MarketState, candles: List = None) -> SetupResult:
        """TREND CONTINUATION PULLBACK"""
        conditions = []
        
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
    
    def _setup_fibonacci(self, state: MarketState) -> SetupResult:
        """FIBONACCI GOLDEN RATIO"""
        conditions = []
        
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
    
    def _setup_vwap_reversion(self, state: MarketState) -> SetupResult:
        """VWAP MEAN REVERSION"""
        conditions = []
        
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
            velocity_data: Dict = None, news_engine=None, move_detector=None) -> Dict:
        """Main analysis - run all indicators and scan all 12 setups"""
        indicators = Indicators(ltf_candles)
        state = indicators.get_all_indicators(htf_candles)
        
        session, can_trade_session = self.get_session()
        
        can_trade, reason = self.can_trade()
        
        # Scan all 12 setups with velocity, news, and funding data for aggressive setups
        setups = self.scan_setups(state, velocity_data, news_engine, move_detector, ltf_candles)
        
        triggered_setup = None
        for result in setups:
            if result.triggered:
                triggered_setup = result
                break
        
        if triggered_setup and can_trade and can_trade_session:
            htf_ok, htf_reason = self.check_htf_alignment(state.htf_bullish, triggered_setup.direction)
            
            if not htf_ok:
                triggered_setup = None
                reason = f"htf_{htf_reason}"
        
        # Apply sentiment modification
        if triggered_setup and self.news_engine:
            risk_mult, lev_boost, blocked = self.news_engine.get_sentiment_modifier(triggered_setup.direction)
            
            if blocked:
                triggered_setup = None
                reason = "sentiment_blocked"
            else:
                triggered_setup.risk_pct *= risk_mult
                triggered_setup.leverage = min(triggered_setup.leverage + lev_boost, 10)
        
        # Apply SESSION-BASED DYNAMIC AGGRESSION
        if triggered_setup:
            session_aggression = self.get_session_aggression()
            
            session_leverage_mod = session_aggression["leverage_mod"]
            session_risk_mult = session_aggression["max_daily_multiplier"]
            
            triggered_setup.leverage = max(1, min(10, triggered_setup.leverage + session_leverage_mod))
            triggered_setup.risk_pct *= session_risk_mult
            
            logger.info(f"SESSION: {session_aggression['session']} | {session_aggression['description']}")
            logger.info(f"Leverage adjusted: +{session_leverage_mod}x | Risk: {session_risk_mult}x")
        
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