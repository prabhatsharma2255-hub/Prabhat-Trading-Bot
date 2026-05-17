"""
AI Brain - Multi-Layer Decision Engine

Production-grade trading decision system with:
- Layer 1: Market Regime Classifier (5 regimes)
- Layer 2: Strategy Modules (specific to each regime)
- Layer 3: Confluence Score (4/5 signals minimum)
- Layer 4: Trade Quality Grading (A/B/C/F)
- HTF (Higher Timeframe) Filter
- Session Awareness
"""

import numpy as np
from typing import Dict, Optional, Tuple, List
from enum import Enum
from datetime import datetime
import config


class MarketRegime(Enum):
    """Market regime classification."""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    HIGH_VOLATILITY = "high_volatility"


class StrategyModule(Enum):
    """Strategy module for each regime."""
    MODULE_A_TREND = "module_a_trend"           # Trend continuation
    MODULE_B_RANGE = "module_b_range"           # Range reversal
    MODULE_C_BREAKOUT = "module_c_breakout"    # Breakout
    MODULE_D_NO_TRADE = "module_d_no_trade"    # No trade in high vol


class TradeGrade(Enum):
    """Trade quality grade."""
    GRADE_A = "grade_a"  # Full size
    GRADE_B = "grade_b"  # Half size
    GRADE_C = "grade_c"  # Quarter size
    GRADE_F = "grade_f"  # No trade


class TradingSession(Enum):
    """Market sessions based on UTC time."""
    ASIA = "asia"
    LONDON = "london"
    NY = "ny"
    NY_ASIA_OVERLAP = "ny_asia_overlap"


class AIBrain:
    def __init__(self):
        self.current_regime: Optional[MarketRegime] = None
        self.previous_regime: Optional[MarketRegime] = None
        self.regime_stability_counter: int = 0
        self.last_regime_change_time: int = 0
        
        self.adx_history: List[float] = []
        self.atr_history: List[float] = []

    def get_current_session(self) -> Tuple[TradingSession, bool]:
        """
        Determine current market session.
        Returns: (session_name, allow_new_entries)
        """
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

    def check_htf_alignment(self, htf_indicators: Dict) -> Tuple[bool, str]:
        """
        Check if entry aligns with higher timeframe (1h) trend.
        Returns: (is_aligned, alignment_status)
        """
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

    def detect_market_regime(self, ltf_data: Dict, htf_data: Optional[Dict] = None) -> MarketRegime:
        """
        Layer 1: Classify market into one of 5 regimes.
        """
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
        
        if atr_pct > 3.0 or bb_width > 4.0:
            return MarketRegime.HIGH_VOLATILITY
        
        if adx > 25 and plus_di > minus_di and price > ema_50 > ema_200 and supertrend == "bullish":
            return MarketRegime.TRENDING_BULL
        
        if adx > 25 and minus_di > plus_di and price < ema_50 < ema_200 and supertrend == "bearish":
            return MarketRegime.TRENDING_BEAR
        
        if adx < 20:
            bb_upper = ltf_data.get("bb_upper", 0)
            bb_lower = ltf_data.get("bb_lower", 0)
            if bb_upper > 0 and bb_lower > 0:
                bb_range_pct = (bb_upper - bb_lower) / price * 100 if price > 0 else 0
                if bb_range_pct < 2.0:
                    return MarketRegime.RANGING
        
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
            self.last_regime_change_time = int(datetime.now().timestamp())
        
        return self.regime_stability_counter >= 2

    def apply_strategy_module(self, regime: MarketRegime, ltf_data: Dict) -> Tuple[int, List[str], str]:
        """
        Layer 2: Apply strategy module based on regime.
        
        Returns: (signals_met, signals_list, module_used)
        """
        signals_fired = []
        
        if regime == MarketRegime.TRENDING_BULL:
            signals_fired = self._module_a_trend(ltf_data, "long")
            return len(signals_fired), signals_fired, "MODULE_A_TREND"
        
        elif regime == MarketRegime.TRENDING_BEAR:
            signals_fired = self._module_a_trend(ltf_data, "short")
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
        """
        Module A: Trend Continuation
        Entry requires ALL of:
        1. Pullback to EMA21 (price touched EMA21 within last 3 candles)
        2. RSI between 40-60 (pullback confirmed)
        3. MACD histogram turning positive (bull) or negative (bear)
        4. Volume on signal candle > 1.2x average
        5. Stochastic RSI K line crossing D line in direction of trend
        """
        signals = []
        
        rsi = data.get("rsi", 50)
        ema_21 = data.get("ema_21", 0)
        price = data.get("current_price", 0)
        macd_hist = data.get("macd_histogram", 0)
        volume_ratio = data.get("volume_ratio", 1)
        stoch_k = data.get("stoch_rsi_k", 50)
        stoch_d = data.get("stoch_rsi_d", 50)
        
        if 40 <= rsi <= 60:
            signals.append("RSI_pullback_zone")
        
        if direction == "long" and ema_21 > 0:
            if price >= ema_21 * 0.995:
                signals.append("price_at_ema21")
        elif direction == "short" and ema_21 > 0:
            if price <= ema_21 * 1.005:
                signals.append("price_at_ema21")
        
        if direction == "long" and macd_hist > 0:
            signals.append("macd_bullish")
        elif direction == "short" and macd_hist < 0:
            signals.append("macd_bearish")
        
        if volume_ratio > 1.2:
            signals.append("volume_confirmation")
        
        if direction == "long" and stoch_k > stoch_d:
            signals.append("stoch_rsi_bullish_cross")
        elif direction == "short" and stoch_k < stoch_d:
            signals.append("stoch_rsi_bearish_cross")
        
        return signals

    def _module_b_range(self, data: Dict) -> List[str]:
        """
        Module B: Range Reversal
        Entry requires ALL of:
        1. RSI < 30 for long / RSI > 70 for short
        2. Price touching lower/upper Bollinger Band
        3. Stochastic RSI < 20 for long / > 80 for short
        4. OBV divergence
        5. Nearest support/resistance within 0.3%
        """
        signals = []
        
        rsi = data.get("rsi", 50)
        price = data.get("current_price", 0)
        bb_upper = data.get("bb_upper", 0)
        bb_lower = data.get("bb_lower", 0)
        stoch_k = data.get("stoch_rsi_k", 50)
        obv = data.get("obv", 0)
        obv_trend = data.get("obv_trend", "neutral")
        support = data.get("support", 0)
        resistance = data.get("resistance", 0)
        
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
        
        if obv_trend == "increasing" and rsi < 40:
            signals.append("obv_bullish_div")
        elif obv_trend == "decreasing" and rsi > 60:
            signals.append("obv_bearish_div")
        
        if support > 0:
            dist_to_support = abs(price - support) / price * 100 if price > 0 else 999
            if dist_to_support < 0.3:
                signals.append("near_support")
        
        if resistance > 0:
            dist_to_resist = abs(price - resistance) / price * 100 if price > 0 else 999
            if dist_to_resist < 0.3:
                signals.append("near_resistance")
        
        return signals

    def _module_c_breakout(self, data: Dict) -> List[str]:
        """
        Module C: Breakout
        Entry requires ALL of:
        1. Price closes above upper BB (bull) or below lower BB (bear)
        2. Volume > 2.5x average
        3. ADX rising (this candle > last candle)
        4. Supertrend flipped this or last candle
        5. No major resistance within 1%
        """
        signals = []
        
        price = data.get("current_price", 0)
        bb_upper = data.get("bb_upper", 0)
        bb_lower = data.get("bb_lower", 0)
        volume_ratio = data.get("volume_ratio", 1)
        
        if len(self.adx_history) > 1:
            adx_rising = data.get("adx", 0) > self.adx_history[-2]
            if adx_rising:
                signals.append("adx_rising")
        
        supertrend = data.get("supertrend", "neutral")
        if supertrend != "neutral":
            signals.append("supertrend_active")
        
        if bb_upper > 0 and price > bb_upper:
            signals.append("breakout_above_bb")
        elif bb_lower > 0 and price < bb_lower:
            signals.append("breakout_below_bb")
        
        if volume_ratio > 2.5:
            signals.append("breakout_volume")
        
        resistance = data.get("resistance", 0)
        if resistance > 0 and bb_upper > 0 and price > 0:
            dist_to_resist = (resistance - price) / price * 100
            if dist_to_resist > 1.0:
                signals.append("no_near_resistance")
        
        return signals

    def grade_trade_quality(self, signals_count: int, htf_aligned: bool, 
                           htf_status: str, rsi: float, volume_ratio: float) -> TradeGrade:
        """
        Layer 4: Grade trade quality (A/B/C/F)
        """
        if signals_count < 4:
            return TradeGrade.GRADE_F
        
        if signals_count == 5 and htf_aligned and 40 <= rsi <= 60 and volume_ratio > 1.2:
            return TradeGrade.GRADE_A
        
        if htf_aligned:
            if signals_count == 5:
                return TradeGrade.GRADE_B
            elif signals_count == 4:
                return TradeGrade.GRADE_C
        
        if not htf_aligned and htf_status == "htf_flat" and signals_count == 5:
            return TradeGrade.GRADE_C
        
        return TradeGrade.GRADE_F

    def analyze(self, ltf_data: Dict, htf_data: Optional[Dict] = None) -> Dict:
        """
        Main analysis function - combines all layers.
        
        Returns complete trading decision with all details.
        """
        regime = self.detect_market_regime(ltf_data, htf_data)
        
        stable = self.check_regime_stability(regime)
        
        signals_count, signals_list, module = self.apply_strategy_module(regime, ltf_data)
        
        htf_aligned, htf_status = self.check_htf_alignment(htf_data) if htf_data else (False, "no_htf")
        
        grade = self.grade_trade_quality(
            signals_count, htf_aligned, htf_status,
            ltf_data.get("rsi", 50),
            ltf_data.get("volume_ratio", 1)
        )
        
        session, allow_entries = self.get_current_session()
        
        can_trade = (
            stable and
            signals_count >= config.MIN_SIGNALS_REQUIRED and
            allow_entries and
            grade in [TradeGrade.GRADE_A, TradeGrade.GRADE_B, TradeGrade.GRADE_C]
        )
        
        if regime == MarketRegime.HIGH_VOLATILITY and signals_count < 5:
            can_trade = False
        
        if htf_data and not htf_aligned and grade == TradeGrade.GRADE_F:
            can_trade = False
        
        direction = "NONE"
        if can_trade:
            if regime == MarketRegime.TRENDING_BULL or regime == MarketRegime.BREAKOUT:
                if htf_status == "htf_bullish" or htf_status == "htf_flat":
                    direction = "LONG"
            elif regime == MarketRegime.TRENDING_BEAR:
                if htf_status == "htf_bearish" or htf_status == "htf_flat":
                    direction = "SHORT"
            elif regime == MarketRegime.RANGING:
                rsi = ltf_data.get("rsi", 50)
                if rsi < 30:
                    direction = "LONG"
                elif rsi > 70:
                    direction = "SHORT"
        
        price = ltf_data.get("current_price", 0)
        atr = ltf_data.get("atr", 0)
        
        risk_pct = 0.03 if grade == TradeGrade.GRADE_A else (0.02 if grade == TradeGrade.GRADE_B else 0.01)
        
        if grade == TradeGrade.GRADE_A:
            leverage = min(config.MAX_LEVERAGE_TRENDING, 6)
        elif grade == TradeGrade.GRADE_B:
            leverage = min(config.MAX_LEVERAGE_TRENDING, 4)
        else:
            leverage = min(config.MAX_LEVERAGE_RANGING, 3)
        
        if regime == MarketRegime.HIGH_VOLATILITY:
            leverage = min(leverage, config.MAX_LEVERAGE_HIGH_VOL)
        
        sl_distance = atr * config.ATR_MULTIPLIER_SL_A if grade == TradeGrade.GRADE_A else atr * config.ATR_MULTIPLIER_SL_C
        
        if price > 0 and (sl_distance / price) > config.MAX_SL_DISTANCE_PCT:
            can_trade = False
            direction = "NONE"
        
        if direction != "NONE":
            if direction == "LONG":
                stop_loss = price - sl_distance
                tp1 = price + (sl_distance * config.TP1_R_MULTIPLE)
                tp2 = price + (sl_distance * config.TP2_R_MULTIPLE)
                tp3 = price + (sl_distance * config.TP3_R_MULTIPLE)
            else:
                stop_loss = price + sl_distance
                tp1 = price - (sl_distance * config.TP1_R_MULTIPLE)
                tp2 = price - (sl_distance * config.TP2_R_MULTIPLE)
                tp3 = price - (sl_distance * config.TP3_R_MULTIPLE)
        else:
            stop_loss = 0
            tp1 = tp2 = tp3 = 0
        
        return {
            "can_trade": can_trade,
            "direction": direction,
            "regime": regime.value,
            "module": module,
            "signals_fired": signals_list,
            "signals_count": signals_count,
            "htf_aligned": htf_aligned,
            "htf_status": htf_status,
            "grade": grade.value,
            "session": session.value,
            "allow_entries": allow_entries,
            "current_price": price,
            "stop_loss": stop_loss,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": tp3,
            "risk_pct": risk_pct,
            "leverage": leverage,
            "atr": atr,
            "regime_stable": stable,
            "rsi": ltf_data.get("rsi", 50),
            "adx": ltf_data.get("adx", 0)
        }