import numpy as np
from typing import List, Dict, Tuple


class TechnicalIndicators:
    def __init__(self, candles: List[Dict]):
        self.candles = candles
        self.close = np.array([float(c.get("close", 0)) for c in candles])
        self.high = np.array([float(c.get("high", 0)) for c in candles])
        self.low = np.array([float(c.get("low", 0)) for c in candles])
        self.volume = np.array([float(c.get("volume", 0)) for c in candles])
        self.open_price = np.array([float(c.get("open", 0)) for c in candles])

    def rsi(self, period: int = 14) -> float:
        if len(self.close) < period + 1:
            return 50.0
        deltas = np.diff(self.close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        if len(self.close) < slow:
            return 0.0, 0.0, 0.0
        ema_fast = self._ema(self.close, fast)
        ema_slow = self._ema(self.close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        histogram = macd_line - signal_line
        return float(macd_line[-1]), float(signal_line[-1]), float(histogram[-1])

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        multiplier = 2 / (period + 1)
        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        return ema

    def bollinger_bands(self, period: int = 20, num_std: float = 2.0) -> Tuple[float, float, float]:
        if len(self.close) < period:
            return 0.0, 0.0, 0.0
        sma = np.mean(self.close[-period:])
        std = np.std(self.close[-period:])
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return float(upper), float(sma), float(lower)

    def ema_list(self) -> Dict[str, float]:
        return {
            "ema_9": float(self._ema(self.close, 9)[-1]) if len(self.close) >= 9 else 0,
            "ema_21": float(self._ema(self.close, 21)[-1]) if len(self.close) >= 21 else 0,
            "ema_50": float(self._ema(self.close, 50)[-1]) if len(self.close) >= 50 else 0,
            "ema_200": float(self._ema(self.close, 200)[-1]) if len(self.close) >= 200 else 0
        }

    def atr(self, period: int = 14) -> float:
        if len(self.high) < period + 1:
            return 0.0
        high_low = self.high[1:] - self.low[1:]
        high_close = np.abs(self.high[1:] - self.close[:-1])
        low_close = np.abs(self.low[1:] - self.close[:-1])
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        return float(np.mean(tr[-period:]))

    def volume_analysis(self) -> Dict[str, float]:
        if len(self.volume) < 20:
            return {"avg_volume": 0, "volume_ratio": 1, "trend": "neutral"}
        avg_volume = np.mean(self.volume[-20:])
        current_volume = self.volume[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        volume_ma5 = np.mean(self.volume[-5:])
        volume_ma20 = np.mean(self.volume[-20:])
        trend = "increasing" if volume_ma5 > volume_ma20 else "decreasing"

        return {"avg_volume": float(avg_volume), "volume_ratio": float(volume_ratio), "trend": trend}

    def stochastic_rsi(self) -> Tuple[float, float]:
        return 50.0, 50.0

    def supertrend(self) -> Tuple[str, float]:
        return "neutral", self.atr(10)

    def vwap(self) -> float:
        if len(self.close) < 1:
            return 0.0
        typical_price = (self.high + self.low + self.close) / 3
        vwap = np.cumsum(typical_price * self.volume) / np.cumsum(self.volume)
        return float(vwap[-1])

    def adx(self) -> Tuple[float, str]:
        return 20.0, "moderate"

    def obv(self) -> Tuple[float, str]:
        obv = 0
        for i in range(1, len(self.close)):
            if self.close[i] > self.close[i-1]:
                obv += self.volume[i]
            elif self.close[i] < self.close[i-1]:
                obv -= self.volume[i]
        return float(obv), "neutral"

    def candlestick_patterns(self) -> Dict[str, int]:
        return {"signal": 0, "pattern": "none"}

    def support_resistance(self) -> Tuple[float, float]:
        if len(self.high) < 20:
            return 0.0, 0.0
        return float(max(self.high[-20:])), float(min(self.low[-20:]))

    def all_indicators(self) -> Dict:
        rsi = self.rsi()
        macd, signal, hist = self.macd()
        bb_upper, bb_middle, bb_lower = self.bollinger_bands()
        ema = self.ema_list()
        atr = self.atr()
        volume = self.volume_analysis()
        stoch_k, stoch_d = self.stochastic_rsi()
        supertrend_dir, supertrend_atr = self.supertrend()
        vwap = self.vwap()
        adx, adx_strength = self.adx()
        obv, obv_trend = self.obv()
        pattern = self.candlestick_patterns()
        resistance, support = self.support_resistance()

        return {
            "rsi": rsi,
            "macd": macd,
            "macd_signal": signal,
            "macd_histogram": hist,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "ema_9": ema.get("ema_9", 0),
            "ema_21": ema.get("ema_21", 0),
            "ema_50": ema.get("ema_50", 0),
            "ema_200": ema.get("ema_200", 0),
            "atr": atr,
            "volume_ratio": volume.get("volume_ratio", 1),
            "volume_trend": volume.get("trend", "neutral"),
            "stoch_rsi_k": stoch_k,
            "stoch_rsi_d": stoch_d,
            "supertrend": supertrend_dir,
            "supertrend_atr": supertrend_atr,
            "vwap": vwap,
            "adx": adx,
            "adx_strength": adx_strength,
            "obv": obv,
            "obv_trend": obv_trend,
            "pattern_signal": pattern.get("signal", 0),
            "pattern_name": pattern.get("pattern", "none"),
            "resistance": resistance,
            "support": support,
            "current_price": float(self.close[-1])
        }