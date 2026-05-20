"""
Bybit Unified Trading API Client

Wraps pybit SDK (official, proven working signature) + public endpoints.
Provides the same interface as the previous custom implementation.
"""

import time
import json
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://api.bybit.com"

RETRY_DELAYS = [2, 4, 8]
MAX_RETRIES = 3


class BybitClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()

        from pybit.unified_trading import HTTP
        self._pybit = HTTP(
            testnet=False,
            api_key=api_key,
            api_secret=api_secret
        )

        self._candle_cache: Dict[str, List[Dict]] = {}
        self._last_candle_time: int = 0
        self.symbol = config.SYMBOL

    def _public_request(self, path: str, params: Optional[Dict] = None,
                        timeout: int = 10, retries: int = MAX_RETRIES) -> Any:
        params = params or {}
        for attempt in range(retries):
            try:
                response = self.session.get(BASE_URL + path, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Public API request error: {e}")
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAYS[attempt])
        return None

    def test_connection(self) -> Dict[str, Any]:
        result = {
            "api_reachable": False,
            "symbol_found": None,
            "candles_retrieved": 0,
            "last_candle_time": None,
            "balance": 0.0,
            "errors": []
        }
        try:
            ticker = self.get_ticker()
            result["api_reachable"] = True
            if ticker:
                result["symbol_found"] = self.symbol
        except Exception as e:
            result["errors"].append(f"Ticker test: {e}")
        try:
            candles = self.get_candles(self.symbol, "15m", 100)
            result["candles_retrieved"] = len(candles) if candles else 0
            if candles:
                result["last_candle_time"] = datetime.fromtimestamp(candles[-1].get("time", 0)).isoformat()
        except Exception as e:
            result["errors"].append(f"Candle fetch: {e}")
        try:
            balance = self.get_balance()
            result["balance"] = balance
        except Exception as e:
            result["errors"].append(f"Balance check: {e}")
        return result

    def get_ticker(self, symbol: Optional[str] = None) -> Optional[Dict]:
        sym = (symbol or self.symbol).upper()
        data = self._public_request("/v5/market/tickers", {"category": "linear", "symbol": sym})
        if data and data.get("result"):
            result = data["result"]
            if result.get("list"):
                return result["list"][0]
        return None

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        sym = symbol.upper()
        interval_map = {
            "1m": "1", "3m": "3", "5m": "5",
            "15m": "15", "30m": "30",
            "1h": "60", "2h": "120", "4h": "240",
            "6h": "360", "12h": "720",
            "1d": "D", "1w": "W"
        }
        interval = interval_map.get(timeframe, "15")
        cache_key = f"{sym}_{interval}_{limit}"

        for attempt in range(MAX_RETRIES):
            try:
                data = self._public_request("/v5/market/kline", {
                    "category": "linear", "symbol": sym, "interval": interval, "limit": limit
                }, timeout=15)
                if not data or data.get("retCode") != 0:
                    continue
                raw_list = data.get("result", {}).get("list", [])
                if not raw_list:
                    continue
                candles = []
                for c in raw_list:
                    ts = int(c[0])
                    candles.append({
                        "open": float(c[1]), "high": float(c[2]),
                        "low": float(c[3]), "close": float(c[4]),
                        "volume": float(c[5]),
                        "close_time": ts / 1000, "time": ts / 1000
                    })
                if candles:
                    candles.reverse()
                    self._candle_cache[cache_key] = candles
                    self._last_candle_time = candles[-1].get("time", 0)
                    logger.info(f"Retrieved {len(candles)} candles for {sym} {timeframe}")
                    return candles
            except Exception as e:
                logger.error(f"Error fetching candles: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])

        cached = self._candle_cache.get(cache_key, [])
        if cached:
            logger.warning(f"Using cached candles: {len(cached)}")
            return cached
        return []

    def get_balance(self) -> float:
        try:
            result = self._pybit.get_wallet_balance(accountType="UNIFIED")
            if result and result.get("list"):
                for coin in result["list"]:
                    if coin.get("coin") == "USDT":
                        return float(coin.get("available", 0))
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return 0.0

    def get_positions(self) -> List[Dict]:
        try:
            result = self._pybit.get_positions(category="linear", symbol=self.symbol.upper())
            if result and result.get("list"):
                positions = []
                for pos in result["list"]:
                    size = float(pos.get("size", 0))
                    if abs(size) > 0:
                        positions.append({
                            "size": abs(size),
                            "side": "buy" if size > 0 else "sell",
                            "entry_price": float(pos.get("avgPrice", 0)),
                            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                            "leverage": int(pos.get("leverage", 1)),
                            "stop_loss": float(pos.get("stopLoss", 0) or 0),
                            "take_profit": float(pos.get("takeProfit", 0) or 0)
                        })
                return positions
        except Exception as e:
            logger.error(f"Positions error: {e}")
        return []

    def get_open_orders(self) -> List[Dict]:
        try:
            result = self._pybit.get_open_orders(category="linear", symbol=self.symbol.upper())
            if result and result.get("list"):
                return result["list"]
        except Exception as e:
            logger.error(f"Open orders error: {e}")
        return []

    def place_order(self, order_type: str, side: str, size: float,
                    price: Optional[float] = None,
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None,
                    leverage: int = 1) -> Optional[Dict]:
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would place: {order_type} {side} {size} @ {price or 'market'} | SL: {stop_loss} | TP: {take_profit} | Lev: {leverage}x")
            return {"orderId": "dry_run_order", "status": "NEW", "dry_run": True}

        try:
            self.set_leverage(leverage)
        except:
            pass

        params = {
            "category": "linear",
            "symbol": self.symbol.upper(),
            "side": side.title(),
            "orderType": order_type.title(),
            "qty": str(size),
            "leverage": str(leverage)
        }
        if order_type == "limit" and price:
            params["price"] = str(price)
            params["timeInForce"] = "GTC"

        try:
            result = self._pybit.place_order(**params)
            if result and result.get("orderId"):
                logger.info(f"Order placed: {result.get('orderId')}")
                if stop_loss:
                    try:
                        self._pybit.place_order(
                            category="linear", symbol=self.symbol.upper(),
                            side="Sell" if side.title() == "Buy" else "Buy",
                            orderType="Market", qty=str(size),
                            stopLoss=str(stop_loss), triggerDirection=1
                        )
                    except:
                        pass
                if take_profit:
                    try:
                        self._pybit.place_order(
                            category="linear", symbol=self.symbol.upper(),
                            side="Sell" if side.title() == "Buy" else "Buy",
                            orderType="Market", qty=str(size),
                            takeProfit=str(take_profit), triggerDirection=2
                        )
                    except:
                        pass
                return result
            logger.error(f"Order placement failed: {result}")
        except Exception as e:
            logger.error(f"Order placement error: {e}")
        return None

    def close_position(self, direction: str, size: float) -> Optional[Dict]:
        close_side = "Sell" if direction == "LONG" else "Buy"
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would close: {close_side} {size}")
            return {"orderId": "dry_run_close", "dry_run": True}
        try:
            result = self._pybit.place_order(
                category="linear", symbol=self.symbol.upper(),
                side=close_side, orderType="Market", qty=str(size)
            )
            return result
        except Exception as e:
            logger.error(f"Close position error: {e}")
        return None

    def cancel_order(self, order_id: str) -> bool:
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True
        try:
            self._pybit.cancel_order(
                category="linear", symbol=self.symbol.upper(), orderId=order_id
            )
            return True
        except:
            return False

    def set_leverage(self, leverage: int, symbol: Optional[str] = None) -> bool:
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would set leverage to {leverage}x")
            return True
        sym = (symbol or self.symbol).upper()
        try:
            self._pybit.set_leverage(
                category="linear", symbol=sym,
                buyLeverage=str(leverage), sellLeverage=str(leverage)
            )
            return True
        except Exception as e:
            logger.error(f"Set leverage error: {e}")
            return False

    def get_market_data(self) -> Dict:
        ticker = self.get_ticker()
        if not ticker:
            return {}
        return {
            "last_price": float(ticker.get("lastPrice", 0)),
            "bid": float(ticker.get("bid1Price", 0)),
            "ask": float(ticker.get("ask1Price", 0)),
            "24h_high": float(ticker.get("highPrice24h", 0)),
            "24h_low": float(ticker.get("lowPrice24h", 0)),
            "24h_volume": float(ticker.get("volume24h", 0)),
            "mark_price": float(ticker.get("markPrice", 0)),
            "index_price": float(ticker.get("indexPrice", 0)),
            "funding_rate": float(ticker.get("fundingRate", 0))
        }

    def get_order_book(self, symbol: Optional[str] = None, depth: int = 20) -> Optional[Dict]:
        sym = (symbol or self.symbol).upper()
        return self._public_request("/v5/market/depth", {
            "category": "linear", "symbol": sym, "limit": depth
        })