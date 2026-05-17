"""
AI Brain - Multi-Layer Decision Engine with Dual Trade Modes

DUAL MODE SYSTEM:
- Mode 1: Conviction Trade (4-5/5 signals, full size, higher leverage)
- Mode 2: Calculated Risk Trade (3/5 signals + price action, smaller size)

PATTERN MEMORY:
- Tracks last 50 trades in SQLite
- Computes win rate by regime, session, signal count
- Adjusts sizing based on historical performance
"""

import numpy as np
import sqlite3
from typing import Dict, Optional, Tuple, List
from enum import Enum
from datetime import datetime
import logging
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    HIGH_VOLATILITY = "high_volatility"


class TradeMode(Enum):
    """Trade mode selection."""
    MODE1_CONVICTION = "mode1_conviction"     # High confidence
    MODE2_CALCULATED = "mode2_calculated"      # Risk mode
    NO_TRADE = "no_trade"


class TradingSession(Enum):
    """Market sessions based on UTC time."""
    ASIA = "asia"
    LONDON = "london"
    NY = "ny"
    NY_ASIA_OVERLAP = "ny_asia_overlap"


class PatternMemory:
    """
    Pattern Memory - The "Own Brain" Component
    
    Tracks trade history and learns where the bot wins/loses.
    Adjusts sizing based on historical performance.
    """
    
    def __init__(self):
        self.db_file = "trades.db"
        self._init_table()
    
    def _init_table(self):
        """Initialize pattern memory table."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS pattern_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            regime TEXT,
            session TEXT,
            mode INTEGER,
            signals_count INTEGER,
            direction TEXT,
            pnl REAL,
            outcome TEXT
        )''')
        conn.commit()
        conn.close()
    
    def record_trade(self, regime: str, session: str, mode: int, 
                    signals_count: int, direction: str, pnl: float, outcome: str):
        """Record a trade for pattern analysis."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''INSERT INTO pattern_memory 
            (timestamp, regime, session, mode, signals_count, direction, pnl, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (datetime.now().isoformat(), regime, session, mode, signals_count, direction, pnl, outcome))
        conn.commit()
        conn.close()
    
    def get_total_trades(self) -> int:
        """Get total recorded trades."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pattern_memory")
        count = c.fetchone()[0]
        conn.close()
        return count
    
    def get_win_rate_by_regime_session(self, regime: str, session: str, mode: int) -> Tuple[float, int]:
        """Get win rate for specific regime + session + mode combination."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute("""SELECT COUNT(*), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) 
            FROM pattern_memory 
            WHERE regime = ? AND session = ? AND mode = ?""",
            (regime, session, mode))
        
        total, wins = c.fetchone()
        conn.close()
        
        if total and total >= config.PATTERN_MEMORY_MIN_SAMPLES:
            return wins / total, total
        return 0.0, 0
    
    def get_mode2_stats(self) -> Dict:
        """Get Mode 2 specific statistics."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute("""SELECT regime, session, COUNT(*) as count, 
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM pattern_memory WHERE mode = 2 GROUP BY regime, session""")
        
        results = c.fetchall()
        conn.close()
        
        stats = {}
        for row in results:
            regime, session, count, wins = row
            key = f"{regime}_{session}"
            stats[key] = {
                "total": count,
                "wins": wins or 0,
                "win_rate": wins/count if count > 0 else 0
            }
        return stats
    
    def should_skip_mode2(self, regime: str, session: str) -> bool:
        """Check if Mode 2 should be skipped based on poor performance."""
        win_rate, samples = self.get_win_rate_by_regime_session(regime, session, mode=2)
        
        if samples < config.PATTERN_MEMORY_MIN_SAMPLES:
            return False  # Not enough data
        
        return win_rate < config.PATTERN_MEMORY_REDUCE_THRESHOLD
    
    def should_boost_mode2(self, regime: str, session: str) -> bool:
        """Check if Mode 2 size should be boosted."""
        win_rate, samples = self.get_win_rate_by_regime_session(regime, session, mode=2)
        
        if samples < config.PATTERN_MEMORY_MIN_SAMPLES:
            return False
        
        return win_rate > config.PATTERN_MEMORY_BOOST_THRESHOLD


class AIBrain:
    def __init__(self):
        self.current_regime: Optional[MarketRegime] = None
        self.previous_regime: Optional[MarketRegime] = None
        self.regime_stability_counter: int = 0
        
        self.adx_history: List[float] = []
        self.atr_history: List[float] = []
        
        self.mode1_trades_today: int = 0
        self.mode2_trades_today: int = 0
        self.mode2_consecutive_losses: int = 0
        
        self.pattern_memory = PatternMemory()
        
        self.candlesticks_cache = []
    
    def get_current_session(self) -> Tuple[TradingSession, bool]:
        """Determine current market session."""
        utc_hour = datetime.utcnow().hour
        
        if 2 <= utc_hour < 9:
            return TradingSession.ASIA, True
        elif 7 <= utc_hour < 16:
            return TradingSession.LONDON, True
        elif 13 <= utc_hour < 22:
            return TradingSession.NY, True
        elif 22 <= utc_hour or utc_hour < 2:
            return TradingSession.NY_ASIA_OVERLAP, False
        
        return TradingSession.NY, True
    
    def reset_daily_counters(self):
        """Reset daily trade counters."""
        self.mode1_trades_today = 0
        self.mode2_trades_today = 0
    
    def check_htf_alignment(self, htf_indicators: Dict) -> Tuple[bool, str]:
        """Check if entry aligns with higher timeframe (1h) trend."""
        if not htf_indicators:
            return False, "no_htf_data"
        
        ema_50 = htf_indicators.get("ema_50", 0)
        ema_50_prev = htf_indicators.get("ema_50_prev", 0)
        
        if ema_50 == 0 or ema_50_prev == 0:
            return False, "no_ema_data"
        
        if ema_50 > ema_50_prev * 1.001:
            return True, "htf_bullish"
        elif ema_50 < ema_50_prev * 0.999:
            return True, "htf_bearish"
        
        return False, "htf_flat"
    
    def detect_market_regime(self, ltf_data: Dict) -> MarketRegime:
        """Layer 1: Classify market into one of 5 regimes."""
        price = ltf_data.get("current_price", 0)
        adx = ltf_data.get("adx", 0)
        plus_di = ltf_data.get("plus_di", 0)
        minus_di = ltf_data.get("minus_di", 0)
        
        ema_9 = ltf_data.get("ema_9", 0)
        ema_21 = ltf_data.get("ema_21", 0)
        ema_50 = ltf_data.get("ema_50", 0)
        ema_200 = ltf_data.get("ema_200", 0)
        
        supertrend = ltf_data.get("supertrend", "neutral")
        atr_pct = ltf_data.get("atr_pct", 0)
        bb_width = ltf_data.get("bb_width", 0)
        
        self.adx_history.append(adx)
        self.atr_history.append(atr_pct)
        
        if len(self.adx_history) > 20:
            self.adx_history.pop(0)
        if len(self.atr_history) > 20:
            self.atr_history.pop(0)
        
        prev_adx = self.adx_history[-2] if len(self.adx_history) > 1 else adx
        
        # High volatility check
        if atr_pct > 3.0 or bb_width > 4.0:
            return MarketRegime.HIGH_VOLATILITY
        
        # Trending Bull
        if adx > 25 and plus_di > minus_di and price > ema_50 > ema_200 and supertrend == "bullish":
            return MarketRegime.TRENDING_BULL
        
        # Trending Bear
        if adx > 25 and minus_di > plus_di and price < ema_50 < ema_200 and supertrend == "bearish":
            return MarketRegime.TRENDING_BEAR
        
        # Ranging
        if adx < 20:
            bb_upper = ltf_data.get("bb_upper", 0)
            bb_lower = ltf_data.get("bb_lower", 0)
            if bb_upper > 0 and bb_lower > 0:
                bb_range_pct = (bb_upper - bb_lower) / price * 100 if price > 0 else 0
                if bb_range_pct < 2.0:
                    return MarketRegime.RANGING
        
        # Breakout
        if prev_adx < 20 and adx > 25:
            bb_upper = ltf_data.get("bb_upper", 0)
            bb_lower = ltf_data.get("bb_lower", 0)
            volume_ratio = ltf_data.get("volume_ratio", 1)
            
            if len(self.atr_history) > 10:
                prev_atr = self.atr_history[-10]
                atr_expanding = atr_pct > prev_atr * 1.5 if prev_atr > 0 else False
            else:
                atr_expanding = False
            
            if (price > bb_upper or price < bb_lower) and volume_ratio > 2.0 and atr_expanding:
                return MarketRegime.BREAKOUT
        
        # Default to trending based on DI
        if adx > 20:
            if plus_di > minus_di:
                return MarketRegime.TRENDING_BULL
            else:
                return MarketRegime.TRENDING_BEAR
        
        return MarketRegime.RANGING
    
    def check_regime_stability(self, regime: MarketRegime) -> bool:
        """Check if regime has been stable for 2 consecutive candles."""
        if regime == self.current_regime:
            self.regime_stability_counter += 1
        else:
            self.previous_regime = self.current_regime
            self.current_regime = regime
            self.regime_stability_counter = 1
        
        return self.regime_stability_counter >= 2
    
    def detect_price_action(self, ltf_data: Dict, direction: str) -> bool:
        """Detect price action signals for Mode 2."""
        if not config.REQUIRE_PRICE_ACTION:
            return True
        
        price = ltf_data.get("current_price", 0)
        ema_21 = ltf_data.get("ema_21", 0)
        
        # Check 1: Price bounced off EMA21 (with candle body, not just wick)
        if ema_21 > 0:
            if direction == "LONG" and price >= ema_21 * 0.995:
                return True
            elif direction == "SHORT" and price <= ema_21 * 1.005:
                return True
        
        # Check 2: Bullish/Bearish engulfing (simple version)
        # Would need more candles for full implementation
        
        # Check 3: Break and hold S/R (simplified)
        support = ltf_data.get("support", 0)
        resistance = ltf_data.get("resistance", 0)
        
        if direction == "LONG" and resistance > 0:
            if price > resistance * 0.998:  # Broke resistance
                return True
        elif direction == "SHORT" and support > 0:
            if price < support * 1.002:  # Broke support
                return True
        
        return False
    
    def apply_strategy_module(self, regime: MarketRegime, ltf_data: Dict) -> Tuple[int, List[str], str]:
        """Apply strategy module based on regime."""
        signals_fired = []
        
        if regime in [MarketRegime.TRENDING_BULL, MarketRegime.TRENDING_BEAR]:
            direction = "long" if regime == MarketRegime.TRENDING_BULL else "short"
            signals_fired = self._module_a_trend(ltf_data, direction)
            return len(signals_fired), signals_fired, "MODULE_A_TREND"
        
        elif regime == MarketRegime.RANGING:
            signals_fired = self._module_b_range(ltf_data)
            return len(signals_fired), signals_fired, "MODULE_B_RANGE"
        
        elif regime == MarketRegime.BREAKOUT:
            signals_fired = self._module_c_breakout(ltf_data)
            return len(signals_fired), signals_fired, "MODULE_C_BREAKOUT"
        
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return 0, [], "MODULE_D_NO_TRADE"
        
        return 0, [], "MODULE_D_NO_TRADE"
    
    def _module_a_trend(self, data: Dict, direction: str) -> List[str]:
        """Module A: Trend Continuation (4-5 signals)"""
        signals = []
        
        rsi = data.get("rsi", 50)
        ema_21 = data.get("ema_21", 0)
        price = data.get("current_price", 0)
        macd_hist = data.get("macd_histogram", 0)
        volume_ratio = data.get("volume_ratio", 1)
        stoch_k = data.get("stoch_rsi_k", 50)
        stoch_d = data.get("stoch_rsi_d", 50)
        
        # RSI pullback zone
        if 40 <= rsi <= 60:
            signals.append("RSI_pullback")
        
        # Price at EMA21
        if direction == "long" and ema_21 > 0 and price >= ema_21 * 0.995:
            signals.append("price_at_ema21")
        elif direction == "short" and ema_21 > 0 and price <= ema_21 * 1.005:
            signals.append("price_at_ema21")
        
        # MACD direction
        if direction == "long" and macd_hist > 0:
            signals.append("macd_bullish")
        elif direction == "short" and macd_hist < 0:
            signals.append("macd_bearish")
        
        # Volume confirmation
        if volume_ratio > 1.2:
            signals.append("volume_confirmation")
        
        # Stochastic cross
        if direction == "long" and stoch_k > stoch_d:
            signals.append("stoch_cross")
        elif direction == "short" and stoch_k < stoch_d:
            signals.append("stoch_cross")
        
        return signals
    
    def _module_b_range(self, data: Dict) -> List[str]:
        """Module B: Range Reversal"""
        signals = []
        
        rsi = data.get("rsi", 50)
        price = data.get("current_price", 0)
        bb_upper = data.get("bb_upper", 0)
        bb_lower = data.get("bb_lower", 0)
        stoch_k = data.get("stoch_rsi_k", 50)
        
        if rsi < 30:
            signals.append("rsi_oversold")
        elif rsi > 70:
            signals.append("rsi_overbought")
        
        if bb_lower > 0 and price <= bb_lower * 1.005:
            signals.append("at_lower_bb")
        elif bb_upper > 0 and price >= bb_upper * 0.995:
            signals.append("at_upper_bb")
        
        if stoch_k < 20:
            signals.append("stoch_oversold")
        elif stoch_k > 80:
            signals.append("stoch_overbought")
        
        return signals
    
    def _module_c_breakout(self, data: Dict) -> List[str]:
        """Module C: Breakout"""
        signals = []
        
        price = data.get("current_price", 0)
        bb_upper = data.get("bb_upper", 0)
        bb_lower = data.get("bb_lower", 0)
        volume_ratio = data.get("volume_ratio", 1)
        
        if len(self.adx_history) > 1:
            if data.get("adx", 0) > self.adx_history[-2]:
                signals.append("adx_rising")
        
        if data.get("supertrend", "neutral") != "neutral":
            signals.append("supertrend_active")
        
        if bb_upper > 0 and price > bb_upper:
            signals.append("breakout_above")
        elif bb_lower > 0 and price < bb_lower:
            signals.append("breakout_below")
        
        if volume_ratio > 2.5:
            signals.append("breakout_volume")
        
        return signals
    
    def determine_trade_mode(self, signals_count: int, regime: MarketRegime,
                            htf_aligned: bool, htf_status: str,
                            ltf_data: Dict, volume_ratio: float) -> Tuple[TradeMode, str]:
        """
        Determine which trade mode to use based on conditions.
        """
        total_trades = self.pattern_memory.get_total_trades()
        is_learning_mode = total_trades < config.LEARNING_MODE_TRADES
        
        if is_learning_mode:
            logger.info(f"[LEARNING MODE] Trade #{total_trades + 1}")
        
        # Determine direction
        direction = "NONE"
        if htf_status == "htf_bullish":
            direction = "LONG"
        elif htf_status == "htf_bearish":
            direction = "SHORT"
        
        if direction == "NONE":
            return TradeMode.NO_TRADE, "no_htf_direction"
        
        # Check regime-specific limits
        session, allow_entries = self.get_current_session()
        
        # MODE 1: Conviction Trade
        # Requires: 4+ signals + HTF aligned + regime-appropriate
        if signals_count >= config.MIN_SIGNALS_MODE1:
            # Check regime limits
            if regime == MarketRegime.BREAKOUT:
                if self.mode1_trades_today >= 1:
                    return TradeMode.NO_TRADE, "breakout_mode1_limit"
            
            # Mode 1 allowed in trending, breakout, high_vol
            if regime in [MarketRegime.TRENDING_BULL, MarketRegime.TRENDING_BEAR]:
                if self.mode1_trades_today < config.MAX_MODE1_TRADES_DAY:
                    return TradeMode.MODE1_CONVICTION, "mode1_approved"
            
            elif regime == MarketRegime.BREAKOUT:
                return TradeMode.MODE1_CONVICTION, "mode1_breakout"
            
            elif regime == MarketRegime.HIGH_VOLATILITY:
                if self.mode1_trades_today < 1:
                    return TradeMode.MODE1_CONVICTION, "mode1_high_vol"
        
        # MODE 2: Calculated Risk Trade
        # Requires: 3 signals + price action + HTF aligned + volume + regime check
        if signals_count >= config.MIN_SIGNALS_MODE2 and signals_count < config.MIN_SIGNALS_MODE1:
            # Must have price action signal
            has_price_action = self.detect_price_action(ltf_data, direction)
            if not has_price_action:
                return TradeMode.NO_TRADE, "no_price_action"
            
            # Must have HTF alignment (non-negotiable even for Mode 2)
            if not htf_aligned:
                return TradeMode.NO_TRADE, "mode2_htf_not_aligned"
            
            # Volume check
            if volume_ratio < config.MIN_VOLUME_RATIO_MODE2:
                return TradeMode.NO_TRADE, "mode2_low_volume"
            
            # Regime-specific rules
            if regime in [MarketRegime.TRENDING_BULL, MarketRegime.TRENDING_BEAR]:
                # Mode 2 only in trend direction
                if regime == MarketRegime.TRENDING_BULL and direction == "LONG":
                    if self.mode2_trades_today < config.MAX_MODE2_TRADES_DAY:
                        # Check pattern memory
                        if not is_learning_mode and self.pattern_memory.should_skip_mode2(regime.value, session.value):
                            return TradeMode.NO_TRADE, "pattern_memory_skip"
                        return TradeMode.MODE2_CALCULATED, "mode2_approved"
                
                elif regime == MarketRegime.TRENDING_BEAR and direction == "SHORT":
                    if self.mode2_trades_today < config.MAX_MODE2_TRADES_DAY:
                        if not is_learning_mode and self.pattern_memory.should_skip_mode2(regime.value, session.value):
                            return TradeMode.NO_TRADE, "pattern_memory_skip"
                        return TradeMode.MODE2_CALCULATED, "mode2_approved"
            
            elif regime == MarketRegime.RANGING:
                # Mode 2 ONLY in ranging
                if self.mode2_trades_today < 2:  # Max 2 range trades
                    return TradeMode.MODE2_CALCULATED, "mode2_range"
            
            elif regime == MarketRegime.HIGH_VOLATILITY:
                return TradeMode.NO_TRADE, "high_vol_no_mode2"
            
            elif regime == MarketRegime.BREAKOUT:
                return TradeMode.NO_TRADE, "breakout_mode1_only"
        
        return TradeMode.NO_TRADE, "insufficient_signals"
    
    def analyze(self, ltf_data: Dict, htf_data: Optional[Dict] = None) -> Dict:
        """Main analysis function with dual trade modes."""
        regime = self.detect_market_regime(ltf_data)
        stable = self.check_regime_stability(regime)
        
        signals_count, signals_list, module = self.apply_strategy_module(regime, ltf_data)
        
        htf_aligned, htf_status = self.check_htf_alignment(htf_data) if htf_data else (False, "no_htf")
        
        volume_ratio = ltf_data.get("volume_ratio", 1)
        
        # Determine trade mode
        trade_mode, skip_reason = self.determine_trade_mode(
            signals_count, regime, htf_aligned, htf_status,
            ltf_data, volume_ratio
        )
        
        session, allow_entries = self.get_current_session()
        
        price = ltf_data.get("current_price", 0)
        atr = ltf_data.get("atr", 0)
        
        # Calculate trade parameters based on mode
        if trade_mode == TradeMode.MODE1_CONVICTION:
            risk_pct = config.RISK_MODE1_GRADE_A
            leverage = config.MAX_LEV_MODE1_TREND
            if regime == MarketRegime.BREAKOUT:
                leverage = config.MAX_LEV_MODE1_BREAKOUT
            elif regime == MarketRegime.HIGH_VOLATILITY:
                leverage = config.MAX_LEV_MODE1_HIGH_VOL
            
            sl_multiplier = config.ATR_MULTIPLIER_MODE1
            tp1_r = config.TP1_R_MODE1
            tp2_r = config.TP2_R_MODE1
            tp3_r = config.TP3_R_MODE1
            mode = 1
            
        elif trade_mode == TradeMode.MODE2_CALCULATED:
            # Check if should boost
            total_trades = self.pattern_memory.get_total_trades()
            if total_trades >= config.LEARNING_MODE_TRADES and self.pattern_memory.should_boost_mode2(regime.value, session.value):
                risk_pct = config.RISK_MODE2_BOOSTED
            elif self.mode2_consecutive_losses >= 2:
                risk_pct = config.RISK_MODE2_REDUCED
            else:
                risk_pct = config.RISK_MODE2_DEFAULT
            
            leverage = config.MAX_LEV_MODE2
            sl_multiplier = config.ATR_MULTIPLIER_MODE2
            tp1_r = config.TP1_R_MODE2
            tp2_r = config.TP2_R_MODE2
            tp3_r = 0  # No TP3 for Mode 2
            mode = 2
            
            if self.mode2_trades_today >= config.MAX_MODE2_TRADES_DAY:
                trade_mode = TradeMode.NO_TRADE
                skip_reason = "mode2_daily_limit"
        
        else:
            risk_pct = 0
            leverage = 0
            sl_multiplier = 0
            tp1_r = tp2_r = tp3_r = 0
            mode = 0
        
        if trade_mode != TradeMode.NO_TRADE:
            # Calculate stop loss and take profits
            sl_distance = atr * sl_multiplier
            
            if price > 0 and (sl_distance / price) > config.MAX_SL_DISTANCE_PCT:
                trade_mode = TradeMode.NO_TRADE
                skip_reason = "sl_too_wide"
            else:
                if direction := (htf_status == "htf_bullish" and "LONG" or htf_status == "htf_bearish" and "SHORT" or None):
                    if direction == "LONG":
                        stop_loss = price - sl_distance
                        take_profit_1 = price + (sl_distance * tp1_r)
                        take_profit_2 = price + (sl_distance * tp2_r)
                        take_profit_3 = price + (sl_distance * tp3_r) if tp3_r > 0 else 0
                    else:
                        stop_loss = price + sl_distance
                        take_profit_1 = price - (sl_distance * tp1_r)
                        take_profit_2 = price - (sl_distance * tp2_r)
                        take_profit_3 = price - (sl_distance * tp3_r) if tp3_r > 0 else 0
                else:
                    stop_loss = take_profit_1 = take_profit_2 = take_profit_3 = 0
        else:
            stop_loss = take_profit_1 = take_profit_2 = take_profit_3 = 0
        
        can_trade = trade_mode != TradeMode.NO_TRADE and stable and allow_entries
        
        if can_trade:
            if trade_mode == TradeMode.MODE1_CONVICTION:
                self.mode1_trades_today += 1
            else:
                self.mode2_trades_today += 1
        
        return {
            "can_trade": can_trade,
            "trade_mode": trade_mode.value,
            "direction": direction if can_trade else "NONE",
            "regime": regime.value,
            "module": module,
            "signals_fired": signals_list,
            "signals_count": signals_count,
            "htf_aligned": htf_aligned,
            "htf_status": htf_status,
            "session": session.value,
            "allow_entries": allow_entries,
            "current_price": price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "take_profit_3": take_profit_3,
            "risk_pct": risk_pct,
            "leverage": leverage,
            "atr": atr,
            "regime_stable": stable,
            "skip_reason": skip_reason,
            "mode": mode,
            "volume_ratio": volume_ratio,
            "rsi": ltf_data.get("rsi", 50),
            "adx": ltf_data.get("adx", 0)
        }
    
    def record_closed_trade(self, pnl: float, outcome: str, regime: str, session: str, 
                           mode: int, signals_count: int, direction: str):
        """Record trade outcome for pattern memory."""
        self.pattern_memory.record_trade(regime, session, mode, signals_count, direction, pnl, outcome)
        
        if mode == 2:
            if pnl < 0:
                self.mode2_consecutive_losses += 1
            else:
                self.mode2_consecutive_losses = 0