"""
Binance Futures API Client

Production-grade wrapper for Binance USD-M Futures REST API with:
- Exponential backoff retry (3 attempts)
- Error logging with raw responses
- Candle caching for resilience
- HMAC-SHA256 signature authentication
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

BASE_URL = "https://fapi.binance.com"

RETRY_DELAYS = [2, 4, 8]
MAX_RETRIES = 3


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/3.0",
            "X-MBX-APIKEY": self.api_key
        })

        self._candle_cache: Dict[str, List[Dict]] = {}
        self._last_candle_time: int = 0

        self.symbol = config.SYMBOL

    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC-SHA256 signature for authenticated requests."""
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(self, method: str, path: str, params: Optional[Dict] = None,
                 signed: bool = False, timeout: int = 10, retries: int = MAX_RETRIES) -> Any:
        """Make API request with exponential backoff retry."""
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            params["signature"] = self._generate_signature(params)

        url = BASE_URL + path
        if params:
            url += "?" + "&".join([f"{k}={v}" for k, v in params.items()])

        for attempt in range(retries):
            try:
                if method == "GET":
                    response = self.session.get(url, timeout=timeout)
                elif method == "POST":
                    response = self.session.post(url, timeout=timeout)
                elif method == "PUT":
                    response = self.session.put(url, timeout=timeout)
                elif method == "DELETE":
                    response = self.session.delete(url, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                data = response.json()

                if data and isinstance(data, dict) and data.get("code"):
                    logger.error(f"Binance API error: {data.get('msg')}")
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
                    err_msg = err_data.get("msg", e.response.text)
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
                result["last_candle_time"] = datetime.fromtimestamp(candles[-1].get("close_time", 0)).isoformat()
        except Exception as e:
            result["errors"].append(f"Candle fetch: {e}")

        try:
            balance = self.get_balance()
            result["balance"] = balance
        except Exception as e:
            result["errors"].append(f"Balance check: {e}")

        return result

    def get_ticker(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Get ticker data for a symbol."""
        sym = symbol or self.symbol
        sym = sym.upper()
        data = self._request("GET", "/fapi/v1/ticker/24hr", {"symbol": sym})
        return data

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        """Fetch OHLCV candles from the API."""
        sym = symbol.upper()
        interval_map = {
            "1m": "1m", "3m": "3m", "5m": "5m",
            "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h",
            "6h": "6h", "12h": "12h",
            "1d": "1d", "1w": "1w"
        }
        interval = interval_map.get(timeframe, "15m")

        cache_key = f"{sym}_{interval}_{limit}"

        for attempt in range(MAX_RETRIES):
            try:
                data = self._request("GET", "/fapi/v1/klines", {
                    "symbol": sym,
                    "interval": interval,
                    "limit": limit
                }, timeout=15)

                if not data:
                    logger.warning(f"Empty response for candles")
                    continue

                candles = []
                for c in data:
                    candles.append({
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "close_time": int(c[0]) / 1000,
                        "time": int(c[0]) / 1000
                    })

                if candles:
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
        """Get account USDT balance."""
        data = self._request("GET", "/fapi/v2/balance", {}, signed=True)
        if data:
            for item in data:
                if item.get("asset") == "USDT":
                    return float(item.get("availableBalance", 0))
        return 0.0

    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        data = self._request("GET", "/fapi/v2/positionRisk", {"symbol": self.symbol.upper()}, signed=True)
        if data:
            positions = []
            for pos in data:
                size = float(pos.get("positionAmt", 0))
                if abs(size) > 0:
                    positions.append({
                        "size": abs(size),
                        "side": "buy" if size > 0 else "sell",
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "unrealized_pnl": float(pos.get("unRealizedProfit", 0)),
                        "leverage": int(pos.get("leverage", 1)),
                        "isolated": pos.get("isolated", False)
                    })
            return positions
        return []

    def get_open_orders(self) -> List[Dict]:
        """Get open orders for the symbol."""
        data = self._request("GET", "/fapi/v1/openOrders", {"symbol": self.symbol.upper()}, signed=True)
        return data if data else []

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
            "symbol": self.symbol.upper(),
            "side": side.upper(),
            "quantity": size,
            "leverage": leverage
        }

        if order_type == "market":
            order_params["type"] = "MARKET"
        elif order_type == "limit":
            order_params["type"] = "LIMIT"
            order_params["price"] = str(price)
            order_params["timeInForce"] = "GTC"
        else:
            order_params["type"] = order_type.upper()

        if stop_loss:
            sl_params = {
                "symbol": self.symbol.upper(),
                "side": "SELL" if side.upper() == "BUY" else "BUY",
                "type": "STOP_MARKET",
                "stopPrice": str(stop_loss),
                "quantity": size,
                "closePosition": True
            }
            self._request("POST", "/fapi/v1/order", sl_params, signed=True)

        if take_profit:
            tp_params = {
                "symbol": self.symbol.upper(),
                "side": "SELL" if side.upper() == "BUY" else "BUY",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": str(take_profit),
                "quantity": size,
                "closePosition": True
            }
            self._request("POST", "/fapi/v1/order", tp_params, signed=True)

        result = self._request("POST", "/fapi/v1/order", order_params, signed=True)

        if result and result.get("orderId"):
            logger.info(f"Order placed: {result.get('orderId')}")
            return result

        logger.error(f"Order placement failed: {result}")
        return None

    def close_position(self, direction: str, size: float) -> Optional[Dict]:
        """Close an open position by placing opposite order."""
        close_side = "SELL" if direction == "LONG" else "BUY"

        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would close: {close_side} {size}")
            return {"orderId": "dry_run_close", "dry_run": True}

        return self.place_order("market", close_side, size, None, None, None)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True

        result = self._request("DELETE", "/fapi/v1/order", {
            "symbol": self.symbol.upper(),
            "orderId": order_id
        }, signed=True)
        return result is not None

    def set_leverage(self, leverage: int, symbol: Optional[str] = None) -> bool:
        """Set leverage for a symbol."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would set leverage to {leverage}x")
            return True

        sym = (symbol or self.symbol).upper()
        result = self._request("POST", "/fapi/v1/leverage", {
            "symbol": sym,
            "leverage": leverage
        }, signed=True)
        return result is not None

    def get_market_data(self) -> Dict:
        """Get current market data."""
        ticker = self.get_ticker()
        if not ticker:
            return {}

        return {
            "last_price": float(ticker.get("lastPrice", 0)),
            "bid": float(ticker.get("bidPrice", 0)),
            "ask": float(ticker.get("askPrice", 0)),
            "24h_high": float(ticker.get("highPrice", 0)),
            "24h_low": float(ticker.get("lowPrice", 0)),
            "24h_volume": float(ticker.get("volume", 0)),
            "mark_price": float(ticker.get("markPrice", 0)),
            "index_price": float(ticker.get("indexPrice", 0)),
            "funding_rate": float(ticker.get("fundingRate", 0))
        }

    def get_order_book(self, symbol: Optional[str] = None, depth: int = 20) -> Optional[Dict]:
        """Get order book data."""
        sym = (symbol or self.symbol).upper()
        return self._request("GET", "/fapi/v1/depth", {
            "symbol": sym,
            "limit": depth
        })