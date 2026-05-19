"""
Bybit Unified Trading API Client

Production-grade wrapper for Bybit USDT Perpetual (linear) REST API with:
- HMAC-SHA256 signature authentication
- Exponential backoff retry (3 attempts)
- Candle caching for resilience
- Full order lifecycle: market/limit/SL/TP
"""

import time
import hmac
import hashlib
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
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/4.0"
        })

        self._candle_cache: Dict[str, List[Dict]] = {}
        self._last_candle_time: int = 0
        self.symbol = config.SYMBOL

    def _generate_signature(self, timestamp: str, method: str, path: str,
                            params_str: str) -> str:
        """Generate HMAC-SHA256 signature for Bybit v5 API."""
        if method == "GET":
            sorted_params = sorted(params_str.split("&")) if params_str else []
            sign_str = "&".join(sorted_params)
        else:
            sign_str = params_str
        message = timestamp + self.api_key + "5000" + sign_str
        return hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, path: str, params: Optional[Dict] = None,
                 timeout: int = 10, retries: int = MAX_RETRIES) -> Any:
        """Make API request with exponential backoff retry."""
        params = params or {}
        timestamp = str(int(time.time() * 1000))

        if method == "GET":
            params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        else:
            params_str = json.dumps(params) if params else ""

        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": self._generate_signature(timestamp, method, path, params_str),
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }

        url = BASE_URL + path

        for attempt in range(retries):
            try:
                if method == "GET":
                    response = self.session.get(url, headers=headers, params=params, timeout=timeout)
                elif method == "POST":
                    response = self.session.post(url, headers=headers, data=params_str, timeout=timeout)
                elif method == "PUT":
                    response = self.session.put(url, headers=headers, data=params_str, timeout=timeout)
                elif method == "DELETE":
                    response = self.session.delete(url, headers=headers, params=params, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                data = response.json()

                if data and isinstance(data, dict):
                    if data.get("retCode") not in (None, 0, "0", 0):
                        logger.error(f"Bybit API error {data.get('retCode')}: {data.get('retMsg')}")
                        return None

                return data

            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    wait_time = RETRY_DELAYS[attempt]
                    logger.warning(f"Request timeout, retrying in {wait_time}s (attempt {attempt + 1}/{retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request timeout after {retries} attempts: {path}")
                    return None

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code
                try:
                    err_data = e.response.json()
                    err_msg = err_data.get("retMsg", e.response.text)
                except:
                    err_msg = e.response.text
                logger.error(f"HTTP {status}: {err_msg}")
                if status == 429:
                    wait_time = RETRY_DELAYS[attempt]
                    logger.warning(f"Rate limited, retrying in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    return None

            except Exception as e:
                logger.error(f"API request error: {e}")
                return None

        return None

    def _public_request(self, method: str, path: str, params: Optional[Dict] = None,
                        timeout: int = 10, retries: int = MAX_RETRIES) -> Any:
        """Make public (unauthenticated) API request."""
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
        """Run connection test and return diagnostic info."""
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
        """Get 24hr ticker data for a symbol."""
        sym = (symbol or self.symbol).upper()
        data = self._public_request("GET", "/v5/market/tickers", {
            "category": "linear",
            "symbol": sym
        })
        if data and data.get("result"):
            result = data["result"]
            if result.get("list"):
                return result["list"][0]
        return None

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        """Fetch OHLCV candles from the API."""
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
                data = self._public_request("GET", "/v5/market/kline", {
                    "category": "linear",
                    "symbol": sym,
                    "interval": interval,
                    "limit": limit
                }, timeout=15)

                if not data or data.get("retCode") != 0:
                    logger.warning(f"Empty or error response for candles: {data}")
                    continue

                raw_list = data.get("result", {}).get("list", [])
                if not raw_list:
                    logger.warning(f"No candle data returned")
                    continue

                candles = []
                for c in raw_list:
                    ts = int(c[0])
                    candles.append({
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "turnover": float(c[6]) if len(c) > 6 else 0,
                        "close_time": ts / 1000,
                        "time": ts / 1000
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

        logger.error(f"Failed to fetch candles after {MAX_RETRIES} attempts")
        return []

    def get_balance(self) -> float:
        """Get account USDT balance (Unified Trading Account)."""
        data = self._request("GET", "/v5/account/wallet-balance", {
            "accountType": "UNIFIED"
        })
        if data and data.get("list"):
            for coin in data["list"]:
                if coin.get("coin") == "USDT":
                    return float(coin.get("available", 0))
        return 0.0

    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        data = self._request("GET", "/v5/position/list", {
            "category": "linear",
            "symbol": self.symbol.upper()
        })
        if data and data.get("list"):
            positions = []
            for pos in data["list"]:
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
        return []

    def get_open_orders(self) -> List[Dict]:
        """Get open orders for the symbol."""
        data = self._request("GET", "/v5/order/realtime", {
            "category": "linear",
            "symbol": self.symbol.upper()
        })
        if data and data.get("list"):
            return data["list"]
        return []

    def place_order(self, order_type: str, side: str, size: float,
                    price: Optional[float] = None,
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None,
                    leverage: int = 1) -> Optional[Dict]:
        """Place a futures order with optional SL/TP."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would place: {order_type} {side} {size} @ {price or 'market'} | SL: {stop_loss} | TP: {take_profit} | Lev: {leverage}x")
            return {"orderId": "dry_run_order", "status": "NEW", "dry_run": True}

        self.set_leverage(leverage)

        order_params = {
            "category": "linear",
            "symbol": self.symbol.upper(),
            "side": side.title(),
            "orderType": order_type.title(),
            "qty": str(size),
            "leverage": leverage
        }

        if order_type == "limit" and price:
            order_params["price"] = str(price)
            order_params["timeInForce"] = "GTC"

        result = self._request("POST", "/v5/order/create", order_params)

        if result and result.get("orderId"):
            logger.info(f"Order placed: {result.get('orderId')}")

            if stop_loss:
                sl_params = {
                    "category": "linear",
                    "symbol": self.symbol.upper(),
                    "side": "Sell" if side.title() == "Buy" else "Buy",
                    "orderType": "Market",
                    "qty": str(size),
                    "stopLoss": str(stop_loss),
                    "triggerDirection": 1
                }
                self._request("POST", "/v5/order/create", sl_params)

            if take_profit:
                tp_params = {
                    "category": "linear",
                    "symbol": self.symbol.upper(),
                    "side": "Sell" if side.title() == "Buy" else "Buy",
                    "orderType": "Market",
                    "qty": str(size),
                    "takeProfit": str(take_profit),
                    "triggerDirection": 2
                }
                self._request("POST", "/v5/order/create", tp_params)

            return result

        logger.error(f"Order placement failed: {result}")
        return None

    def close_position(self, direction: str, size: float) -> Optional[Dict]:
        """Close an open position by placing opposite order."""
        close_side = "Sell" if direction == "LONG" else "Buy"

        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would close: {close_side} {size}")
            return {"orderId": "dry_run_close", "dry_run": True}

        data = self._request("POST", "/v5/order/create", {
            "category": "linear",
            "symbol": self.symbol.upper(),
            "side": close_side,
            "orderType": "Market",
            "qty": str(size)
        })
        return data

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True

        result = self._request("POST", "/v5/order/cancel", {
            "category": "linear",
            "symbol": self.symbol.upper(),
            "orderId": order_id
        })
        return result is not None

    def set_leverage(self, leverage: int, symbol: Optional[str] = None) -> bool:
        """Set leverage for a symbol."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would set leverage to {leverage}x")
            return True

        sym = (symbol or self.symbol).upper()
        result = self._request("POST", "/v5/position/set-leverage", {
            "category": "linear",
            "symbol": sym,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })
        return result is not None

    def get_market_data(self) -> Dict:
        """Get current market data."""
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
        """Get order book data."""
        sym = (symbol or self.symbol).upper()
        return self._public_request("GET", "/v5/market/depth", {
            "category": "linear",
            "symbol": sym,
            "limit": depth
        })