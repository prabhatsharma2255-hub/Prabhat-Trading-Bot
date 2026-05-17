import numpy as np
from typing import Dict, Tuple
from enum import Enum
import config


class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


class ConfidenceEngine:
    def __init__(self):
        self.regime = MarketRegime.RANGING
        self.regime_confidence = 0.0

    def detect_market_regime(self, indicators: Dict, price: float) -> MarketRegime:
        adx = indicators.get("adx", 0)
        ema_9 = indicators.get("ema_9", 0)
        ema_21 = indicators.get("ema_21", 0)
        ema_50 = indicators.get("ema_50", 0)
        atr = indicators.get("atr", 0)

        volatility_factor = (atr / price * 100) if price > 0 else 0

        if volatility_factor > 2.5:
            self.regime = MarketRegime.HIGH_VOLATILITY
            self.regime_confidence = min(volatility_factor * 10, 100)
        elif volatility_factor < 0.5:
            self.regime = MarketRegime.LOW_VOLATILITY
            self.regime_confidence = 80
        elif adx > 25:
            if ema_9 > ema_21 > ema_50 and price > ema_9:
                self.regime = MarketRegime.TRENDING_UP
                self.regime_confidence = min(adx * 2, 100)
            elif ema_9 < ema_21 < ema_50 and price < ema_9:
                self.regime = MarketRegime.TRENDING_DOWN
                self.regime_confidence = min(adx * 2, 100)
            else:
                self.regime = MarketRegime.RANGING
                self.regime_confidence = 60
        else:
            self.regime = MarketRegime.RANGING
            self.regime_confidence = 55

        return self.regime

    def calculate_confidence(self, indicators: Dict, regime: MarketRegime) -> Tuple[float, str]:
        scores = []

        rsi = indicators.get("rsi", 50)
        if regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
            scores.append(8.0 if (regime == MarketRegime.TRENDING_UP and rsi < 40) or (regime == MarketRegime.TRENDING_DOWN and rsi > 60) else 4.0)
        else:
            if rsi < 30:
                scores.append(8.0)
            elif rsi > 70:
                scores.append(2.0)
            elif rsi > 50:
                scores.append(6.0)
            else:
                scores.append(4.0)

        macd = indicators.get("macd", 0)
        if macd > 0:
            scores.append(7.0 if regime == MarketRegime.TRENDING_UP else 5.0)
        else:
            scores.append(3.0 if regime == MarketRegime.TRENDING_DOWN else 5.0)

        ema_9 = indicators.get("ema_9", 0)
        ema_21 = indicators.get("ema_21", 0)
        price = indicators.get("current_price", 0)
        if ema_9 > ema_21 and price > ema_9:
            scores.append(7.0)
        elif ema_9 < ema_21 and price < ema_9:
            scores.append(3.0)
        else:
            scores.append(5.0)

        adx = indicators.get("adx", 0)
        if adx > 25:
            scores.append(7.0)
        elif adx > 15:
            scores.append(5.0)
        else:
            scores.append(4.0)

        volume_ratio = indicators.get("volume_ratio", 1)
        if volume_ratio > 1.5:
            scores.append(7.0)
        else:
            scores.append(5.0)

        confidence = np.mean(scores) * 10

        if confidence < 30:
            signal = "STRONG_SELL"
        elif confidence < 45:
            signal = "WEAK_SELL"
        elif confidence < 55:
            signal = "NEUTRAL"
        elif confidence < 70:
            signal = "WEAK_BUY"
        elif confidence < 85:
            signal = "STRONG_BUY"
        else:
            signal = "VERY_STRONG_BUY"

        return confidence, signal

    def make_trade_decision(self, confidence: float, regime: MarketRegime, indicators: Dict) -> Dict:
        price = indicators.get("current_price", 0)
        atr = indicators.get("atr", 0)

        if confidence < 45:
            direction = "SHORT"
        elif confidence > 55:
            direction = "LONG"
        else:
            direction = "NONE"

        if confidence >= 85:
            risk_amount = config.MAX_RISK_AMOUNT
            leverage = config.MAX_LEVERAGE
        elif confidence >= 70:
            risk_amount = 4.0
            leverage = 7
        elif confidence >= 60:
            risk_amount = 3.0
            leverage = 5
        elif confidence >= 55:
            risk_amount = 2.0
            leverage = 3
        else:
            risk_amount = 0
            leverage = 1

        if regime == MarketRegime.HIGH_VOLATILITY:
            leverage = min(leverage, 3)
            risk_amount *= 0.5
        elif regime == MarketRegime.LOW_VOLATILITY:
            risk_amount = 0

        stop_loss_dist = atr * config.ATR_MULTIPLIER_SL
        take_profit_dist = atr * config.ATR_MULTIPLIER_TP

        stop_loss = price - stop_loss_dist if direction == "LONG" else price + stop_loss_dist
        take_profit = price + take_profit_dist if direction == "LONG" else price - take_profit_dist

        return {
            "should_trade": confidence >= 55 or confidence <= 45,
            "direction": direction,
            "confidence": confidence,
            "risk_amount": risk_amount,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_loss_distance": stop_loss_dist,
            "take_profit_distance": take_profit_dist,
            "regime": regime.value,
            "current_price": price,
            "atr": atr
        }

    def analyze(self, indicators: Dict, price: float) -> Dict:
        regime = self.detect_market_regime(indicators, price)
        confidence, signal = self.calculate_confidence(indicators, regime)
        decision = self.make_trade_decision(confidence, regime, indicators)

        return {
            "regime": regime.value,
            "regime_confidence": self.regime_confidence,
            "confidence": confidence,
            "signal": signal,
            "decision": decision
        }