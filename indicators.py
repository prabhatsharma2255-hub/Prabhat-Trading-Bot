"""
Technical Indicators Module

Production-grade technical analysis with REAL mathematical implementations:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- EMAs (Exponential Moving Average) - multiple periods
- ATR (Average True Range)
- Stochastic RSI
- ADX (Average Directional Index) - Wilder's method
- Supertrend
- VWAP (Volume Weighted Average Price)
- OBV (On Balance Volume)
- Support/Resistance levels
- Volume analysis
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from enum import Enum


class Signal(Enum):
    OVERBOUGHT = "overbought"
    OVERSOLD = "oversold"
    NEUTRAL = "neutral"


class TrendStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class TechnicalIndicators:
    def __init__(self, candles: List[Dict], min_candles: int = 50):
        if not candles or len(candles) < min_candles:
            raise ValueError(f"Insufficient candles: need {min_candles}, got {len(candles) if candles else 0}")
        
        self.candles = candles
        self.n = len(candles)
        
        self.close = np.array([float(c.get("close", 0)) for c in candles], dtype=np.float64)
        self.high = np.array([float(c.get("high", 0)) for c in candles], dtype=np.float64)
        self.low = np.array([float(c.get("low", 0)) for c in candles], dtype=np.float64)
        self.open_price = np.array([float(c.get("open", 0)) for c in candles], dtype=np.float64)
        self.volume = np.array([float(c.get("volume", 0)) for c in candles], dtype=np.float64)
        
        self._validate_arrays()

    def _validate_arrays(self) -> None:
        """Validate data arrays for NaN/Inf values."""
        if not np.all(np.isfinite(self.close)):
            raise ValueError("Close prices contain NaN or Inf values")
        if not np.all(np.isfinite(self.high)):
            raise ValueError("High prices contain NaN or Inf values")
        if not np.all(np.isfinite(self.low)):
            raise ValueError("Low prices contain NaN or Inf values")

    def rsi(self, period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index)."""
        if self.n < period + 1:
            return 50.0
        
        deltas = np.diff(self.close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(np.clip(rsi, 0, 100))

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA (Exponential Moving Average)."""
        if len(data) < period:
            return np.zeros_like(data)
        
        multiplier = 2.0 / (period + 1)
        ema = np.zeros_like(data, dtype=np.float64)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema

    def macd(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[float, float, float]:
        """Calculate MACD: MACD line, Signal line, Histogram."""
        if self.n < slow_period:
            return 0.0, 0.0, 0.0
        
        ema_fast = self._ema(self.close, fast_period)
        ema_slow = self._ema(self.close, slow_period)
        
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal_period)
        histogram = macd_line - signal_line
        
        return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])

    def bollinger_bands(self, period: int = 20, num_std: float = 2.0) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands: Upper, Middle, Lower."""
        if self.n < period:
            return 0.0, 0.0, 0.0
        
        recent_close = self.close[-period:]
        sma = np.mean(recent_close)
        std = np.std(recent_close)
        
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        
        return float(upper), float(sma), float(lower)

    def ema_list(self) -> Dict[str, float]:
        """Get EMAs for multiple periods."""
        return {
            "ema_9": float(self._ema(self.close, 9)[-1]) if self.n >= 9 else 0.0,
            "ema_21": float(self._ema(self.close, 21)[-1]) if self.n >= 21 else 0.0,
            "ema_50": float(self._ema(self.close, 50)[-1]) if self.n >= 50 else 0.0,
            "ema_200": float(self._ema(self.close, 200)[-1]) if self.n >= 200 else 0.0,
            "ema_9_prev": float(self._ema(self.close, 9)[-2]) if self.n >= 10 else 0.0,
            "ema_21_prev": float(self._ema(self.close, 21)[-2]) if self.n >= 22 else 0.0,
            "ema_50_prev": float(self._ema(self.close, 50)[-2]) if self.n >= 51 else 0.0
        }

    def atr(self, period: int = 14) -> float:
        """Calculate ATR (Average True Range)."""
        if self.n < period + 1:
            return 0.0
        
        high_low = self.high[1:] - self.low[1:]
        high_close = np.abs(self.high[1:] - self.close[:-1])
        low_close = np.abs(self.low[1:] - self.close[:-1])
        
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        atr_value = np.mean(true_range[-period:])
        
        return float(atr_value)

    def atr_pct(self, period: int = 14) -> float:
        """Calculate ATR as percentage of current price."""
        current_price = self.close[-1]
        atr = self.atr(period)
        if current_price > 0:
            return (atr / current_price) * 100
        return 0.0

    def stochastic_rsi(self, rsi_period: int = 14, stoch_period: int = 14, 
                       smooth_k: int = 3, smooth_d: int = 3) -> Tuple[float, float, Signal]:
        """
        Calculate Stochastic RSI.
        
        Formula:
        1. Calculate RSI over rsi_period
        2. Apply Stochastic oscillator to RSI values (not price)
        3. Apply smoothing to K line
        
        Returns: (k_line, d_line, signal)
        """
        if self.n < rsi_period + stoch_period:
            return 50.0, 50.0, Signal.NEUTRAL
        
        rsi_values = []
        for i in range(rsi_period, self.n + 1):
            window = self.close[i - rsi_period:i]
            deltas = np.diff(window)
            gains = np.where(deltas > 0, deltas, 0.0)
            losses = np.where(deltas < 0, -deltas, 0.0)
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                rsi_values.append(rsi)
        
        if len(rsi_values) < stoch_period:
            return 50.0, 50.0, Signal.NEUTRAL
        
        rsi_array = np.array(rsi_values)
        
        stoch_k = []
        for i in range(stoch_period, len(rsi_array) + 1):
            rsi_window = rsi_array[i - stoch_period:i]
            rsi_min = np.min(rsi_window)
            rsi_max = np.max(rsi_window)
            
            if rsi_max - rsi_min == 0:
                stoch_k.append(50.0)
            else:
                k = 100 * (rsi_array[-1] - rsi_min) / (rsi_max - rsi_min)
                stoch_k.append(k)
        
        if len(stoch_k) < smooth_k:
            return 50.0, 50.0, Signal.NEUTRAL
        
        k_values = np.array(stoch_k[-smooth_k:])
        k_smooth = np.mean(k_values)
        
        d_values = np.array(stoch_k[-smooth_d:])
        d_smooth = np.mean(d_values)
        
        if k_smooth > 80:
            signal = Signal.OVERBOUGHT
        elif k_smooth < 20:
            signal = Signal.OVERSOLD
        else:
            signal = Signal.NEUTRAL
        
        return float(k_smooth), float(d_smooth), signal

    def adx(self, period: int = 14) -> Tuple[float, TrendStrength, float, float]:
        """
        Calculate ADX (Average Directional Index) using Wilder's method.
        
        Returns: (adx_value, trend_strength, plus_di, minus_di)
        """
        if self.n < period * 2:
            return 20.0, TrendStrength.MODERATE, 15.0, 15.0
        
        high = self.high[1:]
        low = self.low[1:]
        close = self.close[1:]
        prev_close = self.close[:-1]
        
        plus_dm = np.zeros(len(high))
        minus_dm = np.zeros(len(high))
        
        for i in range(1, len(high)):
            up_move = high[i] - high[i-1]
            down_move = low[i-1] - low[i]
            
            plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0
            minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0
        
        high_low = high - low
        high_close = np.abs(high - prev_close)
        low_close = np.abs(low - prev_close)
        
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        
        smoothed_tr = self._smoothed_ma(true_range, period)
        smoothed_plus_dm = self._smoothed_ma(plus_dm, period)
        smoothed_minus_dm = self._smoothed_ma(minus_dm, period)
        
        plus_di = np.zeros(len(smoothed_tr))
        minus_di = np.zeros(len(smoothed_tr))
        
        for i in range(len(smoothed_tr)):
            if smoothed_tr[i] > 0:
                plus_di[i] = 100 * smoothed_plus_dm[i] / smoothed_tr[i]
                minus_di[i] = 100 * smoothed_minus_dm[i] / smoothed_tr[i]
        
        dx = np.zeros(len(plus_di))
        for i in range(len(dx)):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum
        
        adx_values = self._smoothed_ma(dx, period)
        
        adx_value = adx_values[-1] if len(adx_values) > 0 else 20.0
        plus_di_current = plus_di[-1] if len(plus_di) > 0 else 15.0
        minus_di_current = minus_di[-1] if len(minus_di) > 0 else 15.0
        
        if adx_value > 25:
            strength = TrendStrength.STRONG
        elif adx_value < 20:
            strength = TrendStrength.WEAK
        else:
            strength = TrendStrength.MODERATE
        
        return float(adx_value), strength, float(plus_di_current), float(minus_di_current)

    def _smoothed_ma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate smoothed moving average (Wilder's smoothing)."""
        if len(data) < period:
            return np.zeros_like(data)
        
        result = np.zeros_like(data, dtype=np.float64)
        result[0] = np.mean(data[:period])
        
        for i in range(1, len(data)):
            result[i] = (result[i-1] * (period - 1) + data[i]) / period
        
        return result

    def supertrend(self, period: int = 10, multiplier: float = 3.0) -> Tuple[str, float]:
        """
        Calculate Supertrend indicator.
        
        Formula:
        - Upper Band = (High + Low) / 2 + (Multiplier * ATR)
        - Lower Band = (High + Low) / 2 - (Multiplier * ATR)
        - Trend direction flips when price crosses the bands
        
        Returns: (direction, distance_pct)
        """
        if self.n < period:
            return "neutral", 0.0
        
        atr = self.atr(period)
        hl_avg = (self.high + self.low) / 2
        
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        direction = "neutral"
        prev_close = self.close[-2] if self.n > 1 else self.close[-1]
        current_close = self.close[-1]
        
        prev_upper = upper_band[-2] if self.n > 1 else upper_band[-1]
        prev_lower = lower_band[-2] if self.n > 1 else lower_band[-1]
        
        if current_close > upper_band[-1]:
            direction = "bullish"
        elif current_close < lower_band[-1]:
            direction = "bearish"
        else:
            if prev_close > prev_upper:
                direction = "bullish"
            elif prev_close < prev_lower:
                direction = "bearish"
        
        if direction == "neutral":
            return "neutral", 0.0
        
        band = upper_band[-1] if direction == "bullish" else lower_band[-1]
        distance_pct = ((current_price - band) / current_price * 100) if (current_price := self.close[-1]) > 0 else 0.0
        
        return direction, float(distance_pct)

    def vwap(self) -> float:
        """Calculate VWAP (Volume Weighted Average Price)."""
        if self.n < 1:
            return 0.0
        
        typical_price = (self.high + self.low + self.close) / 3.0
        
        cumulative_tp_vol = np.cumsum(typical_price * self.volume)
        cumulative_vol = np.cumsum(self.volume)
        
        vwap_values = cumulative_tp_vol / cumulative_vol
        
        return float(vwap_values[-1])

    def obv(self) -> Tuple[float, str]:
        """Calculate OBV (On Balance Volume)."""
        if self.n < 2:
            return 0.0, "neutral"
        
        obv_value = 0.0
        for i in range(1, self.n):
            if self.close[i] > self.close[i-1]:
                obv_value += self.volume[i]
            elif self.close[i] < self.close[i-1]:
                obv_value -= self.volume[i]
        
        obv_trend = "neutral"
        if self.n >= 10:
            recent_obv = obv_value
            old_obv = 0.0
            for i in range(1, 10):
                if self.close[i] > self.close[i-1]:
                    old_obv += self.volume[i]
                elif self.close[i] < self.close[i-1]:
                    old_obv -= self.volume[i]
            
            if recent_obv > old_obv:
                obv_trend = "increasing"
            elif recent_obv < old_obv:
                obv_trend = "decreasing"
        
        return float(obv_value), obv_trend

    def volume_analysis(self) -> Dict[str, float]:
        """Analyze volume patterns."""
        if self.n < 20:
            return {"avg_volume": 0.0, "volume_ratio": 1.0, "trend": "neutral"}
        
        avg_volume = float(np.mean(self.volume[-20:]))
        current_volume = float(self.volume[-1])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        volume_ma5 = float(np.mean(self.volume[-5:]))
        volume_ma20 = float(np.mean(self.volume[-20:]))
        
        trend = "neutral"
        if volume_ma5 > volume_ma20 * 1.1:
            trend = "increasing"
        elif volume_ma5 < volume_ma20 * 0.9:
            trend = "decreasing"
        
        return {"avg_volume": avg_volume, "volume_ratio": volume_ratio, "trend": trend}

    def support_resistance(self, lookback: int = 20) -> Tuple[float, float]:
        """Find recent support and resistance levels."""
        if self.n < lookback:
            return 0.0, 0.0
        
        resistance = float(np.max(self.high[-lookback:]))
        support = float(np.min(self.low[-lookback:]))
        
        return resistance, support

    def bollinger_width(self) -> float:
        """Calculate Bollinger Band width as percentage of price."""
        upper, middle, lower = self.bollinger_bands()
        current_price = self.close[-1]
        
        if middle > 0:
            return ((upper - lower) / middle) * 100
        return 0.0

    def candlestick_patterns(self) -> Dict[str, any]:
        """Detect basic candlestick patterns."""
        if self.n < 3:
            return {"pattern": "none", "signal": 0}
        
        last = self.n - 1
        body = abs(self.close[last] - self.open_price[last])
        upper_shadow = self.high[last] - max(self.open_price[last], self.close[last])
        lower_shadow = min(self.open_price[last], self.close[last]) - self.low[last]
        
        if body == 0:
            return {"pattern": "doji", "signal": 0}
        
        if body > (upper_shadow + lower_shadow) * 0.5:
            if self.close[last] > self.open_price[last]:
                return {"pattern": "bullish_body", "signal": 1}
            else:
                return {"pattern": "bearish_body", "signal": -1}
        
        return {"pattern": "neutral", "signal": 0}

    def all_indicators(self) -> Dict:
        """Calculate and return all indicators."""
        rsi = self.rsi()
        macd, macd_signal, macd_hist = self.macd()
        bb_upper, bb_middle, bb_lower = self.bollinger_bands()
        ema = self.ema_list()
        atr = self.atr()
        atr_pct = self.atr_pct()
        stoch_k, stoch_d, stoch_signal = self.stochastic_rsi()
        adx, adx_strength, plus_di, minus_di = self.adx()
        supertrend_dir, supertrend_dist = self.supertrend()
        vwap = self.vwap()
        obv, obv_trend = self.obv()
        volume = self.volume_analysis()
        resistance, support = self.support_resistance()
        bb_width = self.bollinger_width()
        pattern = self.candlestick_patterns()
        
        return {
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
            "ema_9": ema.get("ema_9", 0),
            "ema_21": ema.get("ema_21", 0),
            "ema_50": ema.get("ema_50", 0),
            "ema_200": ema.get("ema_200", 0),
            "ema_9_prev": ema.get("ema_9_prev", 0),
            "ema_21_prev": ema.get("ema_21_prev", 0),
            "ema_50_prev": ema.get("ema_50_prev", 0),
            "atr": atr,
            "atr_pct": atr_pct,
            "stoch_rsi_k": stoch_k,
            "stoch_rsi_d": stoch_d,
            "stoch_rsi_signal": stoch_signal.value,
            "adx": adx,
            "adx_strength": adx_strength.value,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "supertrend": supertrend_dir,
            "supertrend_distance": supertrend_dist,
            "vwap": vwap,
            "obv": obv,
            "obv_trend": obv_trend,
            "volume_ratio": volume.get("volume_ratio", 1),
            "volume_trend": volume.get("trend", "neutral"),
            "resistance": resistance,
            "support": support,
            "pattern": pattern.get("pattern", "none"),
            "pattern_signal": pattern.get("signal", 0),
            "current_price": float(self.close[-1]),
            "timestamp": self.candles[-1].get("time", 0) if self.candles else 0
        }