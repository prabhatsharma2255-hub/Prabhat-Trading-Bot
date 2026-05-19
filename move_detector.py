"""
Move Detector - Real-time explosive move detection

Runs independently every 30 seconds
Detects price velocity, volume explosions, funding rate extremes
Triggers emergency cycles when explosive moves detected
"""

import time
import logging
import threading
import requests
from typing import Dict, List, Optional
from collections import deque

import config
from bybit_client import BybitClient

logger = logging.getLogger(__name__)


class MoveDetector:
    def __init__(self, client: BybitClient):
        self.client = client
        self.price_history: deque = deque(maxlen=20)
        self.volume_history: deque = deque(maxlen=20)
        self.oi_history: deque = deque(maxlen=20)

        self.last_funding_check = 0
        self.last_oi_check = 0

        self.funding_rate = 0
        self.funding_bias = "neutral"
        self.oi_change_pct = 0

        self.last_price = 0
        self.micro_surge = False
        self.momentum_burst = False
        self.explosive_move = False
        self.volume_explosion = False
        self.acceleration = False

        self.emergency_triggered = False
        self.emergency_callback = None

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_emergency_callback(self, callback):
        self.emergency_callback = callback

    def start(self):
        if self._running:
            logger.warning("MoveDetector already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("MoveDetector started (30s intervals)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MoveDetector stopped")

    def _run_loop(self):
        while self._running:
            try:
                self.detect_moves()

                if self.emergency_triggered and self.emergency_callback:
                    self.emergency_callback()
                    self.emergency_triggered = False

            except Exception as e:
                logger.error(f"MoveDetector error: {e}")

            time.sleep(config.MOVE_DETECTOR_INTERVAL_SEC)

    def fetch_price_and_volume(self) -> Optional[Dict]:
        try:
            candles = self.client.get_candles(config.SYMBOL, "1m", 20)

            if candles and len(candles) >= 5:
                current_price = candles[-1].get("close", 0)
                current_volume = candles[-1].get("volume", 0)
                avg_volume = sum(c.get("volume", 0) for c in candles[:-1]) / (len(candles) - 1)

                self.price_history.append(current_price)
                self.volume_history.append(current_volume)

                return {
                    "price": current_price,
                    "avg_volume": avg_volume,
                    "current_volume": current_volume
                }

        except Exception as e:
            logger.error(f"Price/volume fetch error: {e}")

        return None

    def detect_moves(self):
        data = self.fetch_price_and_volume()

        if not data:
            return

        self.last_price = data["price"]

        if len(self.price_history) < 6:
            return

        prices = list(self.price_history)

        vel_1m = (prices[-1] - prices[-2]) / prices[-2] * 100 if len(prices) >= 2 else 0
        vel_3m = (prices[-1] - prices[-4]) / prices[-4] * 100 if len(prices) >= 4 else 0
        vel_5m = (prices[-1] - prices[-6]) / prices[-6] * 100 if len(prices) >= 6 else 0

        self.micro_surge = abs(vel_1m) > config.MICRO_SURGE_PCT
        self.momentum_burst = abs(vel_3m) > 0.8
        self.explosive_move = abs(vel_5m) > config.EXPLOSIVE_MOVE_PCT

        self.acceleration = abs(vel_1m) > (abs(vel_3m) / 3) if vel_3m != 0 else False

        vol_ratio = data["current_volume"] / data["avg_volume"] if data["avg_volume"] > 0 else 1
        self.volume_explosion = vol_ratio > config.VOLUME_EXPLOSION_MULT

        if self.explosive_move:
            self.emergency_triggered = True
            logger.warning(f"EXPLOSIVE MOVE DETECTED: {vel_5m:.2f}% in 5min")

        if self.volume_explosion and (self.micro_surge or self.momentum_burst):
            self.emergency_triggered = True
            logger.warning(f"VOLUME EXPLOSION: {vol_ratio:.1f}x avg - emergency cycle")

    def poll_funding_rate(self):
        now = time.time()

        if now - self.last_funding_check < config.FUNDING_POLL_MIN * 60:
            return

        try:
            # FIXED: Use correct API domain
            url = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                for ticker in data.get("result", []):
                    if ticker.get("symbol") == "BTCUSD":
                        funding = ticker.get("funding_rate", 0)
                        self.funding_rate = funding

                        if funding > config.FUNDING_CROWDED_THRESHOLD:
                            self.funding_bias = "long_crowded"
                        elif funding < -config.FUNDING_CROWDED_THRESHOLD:
                            self.funding_bias = "short_crowded"
                        else:
                            self.funding_bias = "neutral"

                        self.last_funding_check = now
                        break

        except Exception as e:
            logger.error(f"Funding rate poll error: {e}")

    def poll_oi(self):
        now = time.time()

        if now - self.last_oi_check < config.OI_POLL_MIN * 60:
            return

        try:
            # FIXED: Use correct API domain
            url = "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1h"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("list"):
                    current_oi = float(data["list"][0].get("openInterest", 0) or 0)

                if self.oi_history:
                    prev_oi = self.oi_history[-1]
                    if prev_oi > 0:
                        self.oi_change_pct = (current_oi - prev_oi) / prev_oi * 100

                self.oi_history.append(current_oi)
                self.last_oi_check = now

        except Exception as e:
            logger.error(f"OI poll error: {e}")

    def get_market_intelligence(self) -> Dict:
        vel_1m = 0
        vel_3m = 0
        if len(self.price_history) >= 2:
            vel_1m = (self.price_history[-1] - self.price_history[-2]) / self.price_history[-2] * 100
        if len(self.price_history) >= 4:
            vel_3m = (self.price_history[-1] - self.price_history[-4]) / self.price_history[-4] * 100
        return {
            "funding_rate": self.funding_rate,
            "funding_bias": self.funding_bias,
            "oi_change_pct": self.oi_change_pct,
            "micro_surge": self.micro_surge,
            "momentum_burst": self.momentum_burst,
            "explosive_move": self.explosive_move,
            "volume_explosion": self.volume_explosion,
            "velocity_1m": vel_1m,
            "velocity_3m": vel_3m,
        }

    def get_setup_preference(self, direction: str) -> float:
        leverage_mod = 0

        if direction == "LONG":
            if self.funding_bias == "short_crowded":
                leverage_mod = 0.5
            elif self.funding_bias == "long_crowded":
                leverage_mod = -0.5
        elif direction == "SHORT":
            if self.funding_bias == "long_crowded":
                leverage_mod = 0.5
            elif self.funding_bias == "short_crowded":
                leverage_mod = -0.5

        if self.oi_change_pct < 0 and direction == "LONG":
            leverage_mod += 0.5

        if self.oi_change_pct > 0 and direction == "SHORT":
            leverage_mod += 0.5

        return leverage_mod
