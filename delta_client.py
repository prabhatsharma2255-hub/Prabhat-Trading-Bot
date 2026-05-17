"""
Delta Exchange India API Client

Production-grade wrapper for Delta Exchange v2 REST API with:
- Exponential backoff retry (3 attempts)
- Error logging with raw responses
- Candle caching for resilience
- Auto symbol discovery
"""

import time
import hmac
import hashlib
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://api.india.delta.exchange"

RETRY_DELAYS = [2, 4, 8]
MAX_RETRIES = 3


class DeltaClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "User-Agent": "TradingBot/2.0"})
        
        self._symbol_cache: Optional[str] = None
        self._candle_cache: Dict[str, List[Dict]] = {}
        self._last_candle_time: int = 0
        
        self._discover_symbol()

    def _discover_symbol(self) -> None:
        """Dynamically discover the correct BTC USD perpetual symbol."""
        try:
            data = self._public_request(f"{BASE_URL}/v2/products", timeout=15)
            
            if data and "result" in data:
                products = data["result"]
                
                btc_usd_perpetual = [
                    p for p in products
                    if p.get("symbol", "").upper() == "BTCUSD"
                ]
                
                if btc_usd_perpetual:
                    self._symbol_cache = "BTCUSD"
                    logger.info(f"Found BTCUSD perpetual: {self._symbol_cache}")
                    return
                    
                btc_usd = [
                    p for p in products
                    if p.get("symbol", "").upper().startswith("BTC")
                    and "USD" in p.get("description", "").upper()
                ]
                
                if btc_usd:
                    self._symbol_cache = btc_usd[0].get("symbol")
                    logger.info(f"Found BTC USD product: {self._symbol_cache}")
                    return
                    
            logger.warning("Could not discover BTC symbol from products endpoint")
                
        except Exception as e:
            logger.error(f"Error discovering symbol: {e}")
        
        self._symbol_cache = config.SYMBOL
        logger.info(f"Using fallback symbol: {self._symbol_cache}")

    def _generate_signature(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Generate HMAC-SHA256 signature for authenticated requests."""
        timestamp = str(int(time.time()))
        message = timestamp + method + path + body
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return {
            "Delta-Time": timestamp,
            "Delta-Auth": signature,
            "Delta-Api-Key": self.api_key
        }

    def _request(self, method: str, path: str, body: Optional[Dict] = None, 
                 timeout: int = 10, retries: int = MAX_RETRIES) -> Any:
        """Make authenticated API request with exponential backoff retry."""
        url = BASE_URL + path
        body_str = json.dumps(body) if body else ""
        headers = self._generate_signature(method, path, body_str)

        for attempt in range(retries):
            try:
                if method == "GET":
                    response = self.session.get(url, headers=headers, timeout=timeout)
                elif method == "POST":
                    response = self.session.post(url, headers=headers, data=body_str, timeout=timeout)
                elif method == "PUT":
                    response = self.session.put(url, headers=headers, data=body_str, timeout=timeout)
                elif method == "DELETE":
                    response = self.session.delete(url, headers=headers, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    wait_time = RETRY_DELAYS[attempt]
                    logger.warning(f"Request timeout, retrying in {wait_time}s (attempt {attempt + 1}/{retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request timeout after {retries} attempts: {path}")
                    return None

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
                if e.response.status_code == 429:
                    wait_time = RETRY_DELAYS[attempt]
                    logger.warning(f"Rate limited, retrying in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    return None

            except Exception as e:
                logger.error(f"API request error: {e}")
                return None

        return None

    def _public_request(self, url: str, timeout: int = 10) -> Any:
        """Make public (unauthenticated) API request."""
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Public API request error: {e}")
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
            test_ticker = self.get_ticker()
            result["api_reachable"] = True
            if test_ticker:
                result["symbol_found"] = test_ticker.get("symbol")
        except Exception as e:
            result["errors"].append(f"Ticker test: {e}")

        try:
            candles = self.get_candles(self._symbol_cache or config.SYMBOL, "15m", 100)
            result["candles_retrieved"] = len(candles) if candles else 0
            if candles:
                result["last_candle_time"] = datetime.fromtimestamp(candles[0].get("time", 0)).isoformat()
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
        if symbol is None:
            symbol = self._symbol_cache or config.SYMBOL
        data = self._public_request(f"{BASE_URL}/v2/tickers/{symbol}")
        if data and "result" in data:
            return data["result"]
        return None

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        """Fetch OHLCV candles from the API."""
        end_time = int(time.time())
        start_time = end_time - (60 * 60 * 24 * 7)

        resolution_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", 
            "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", 
            "6h": "6h", "12h": "12h",
            "1d": "1d", "1w": "1w"
        }
        resolution = resolution_map.get(timeframe, "15m")

        cache_key = f"{symbol}_{timeframe}_{limit}"
        
        for attempt in range(MAX_RETRIES):
            try:
                url = f"{BASE_URL}/v2/history/candles?symbol={symbol}&resolution={resolution}&start={start_time}&end={end_time}&limit={limit}"
                logger.debug(f"Fetching candles: {url}")

                data = self._public_request(url, timeout=15)
                
                if not data:
                    logger.warning(f"Empty response for candles")
                    continue

                if "error" in data:
                    logger.error(f"API error: {data.get('error')}")
                    if attempt < MAX_RETRIES - 1:
                        wait_time = RETRY_DELAYS[attempt]
                        time.sleep(wait_time)
                        continue
                    return []

                candles = data.get("result", [])
                
                if candles:
                    candles.reverse()
                    self._candle_cache[cache_key] = candles
                    self._last_candle_time = candles[-1].get("time", 0)
                    logger.info(f"Retrieved {len(candles)} candles for {symbol} {timeframe}")
                    return candles
                else:
                    logger.warning(f"No candles returned for {symbol} {timeframe}")

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
        """Get account USD balance."""
        data = self._request("GET", "/v2/wallet/balances")
        if data and "result" in data:
            for balance in data["result"]:
                if balance.get("asset_code") == "USD":
                    return float(balance.get("available_balance", 0))
        return 0.0

    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        data = self._request("GET", "/v2/positions")
        return data.get("result", []) if data else []

    def get_open_orders(self) -> List[Dict]:
        """Get open orders for the symbol."""
        symbol = self._symbol_cache or config.SYMBOL
        data = self._request("GET", f"/v2/orders?product_id={symbol}&state=open")
        return data.get("result", []) if data else []

    def place_order(self, order_type: str, side: str, size: float,
                    price: Optional[float] = None,
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None,
                    leverage: int = 1) -> Optional[Dict]:
        """Place a futures order. SL/TP managed by bot, not exchange."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would place: {order_type} {side} {size} @ {price or 'market'} | SL: {stop_loss} | TP: {take_profit}")
            return {"order_id": "dry_run_order", "state": "open", "dry_run": True}
        
        symbol = self._symbol_cache or config.SYMBOL
        order_params = {
            "product_id": symbol,
            "size": size,
            "side": side,
            "order_type": order_type,
            "leverage": leverage
        }
        
        if price:
            order_params["price"] = str(price)
        
        result = self._request("POST", "/v2/orders", order_params)
        
        if result and "result" in result:
            logger.info(f"Order placed: {result['result'].get('order_id')}")
            return result["result"]
        
        logger.error(f"Order placement failed: {result}")
        return None
    
    def close_position(self, direction: str, size: float) -> Optional[Dict]:
        """Close an open position by placing opposite order."""
        close_side = "sell" if direction == "LONG" else "buy"
        
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would close: {close_side} {size}")
            return {"order_id": "dry_run_close", "dry_run": True}
        
        return self.place_order("market", close_side, size, None, None, None, 1)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True
        
        result = self._request("DELETE", f"/v2/orders/{order_id}")
        return result is not None

    def set_leverage(self, leverage: int, symbol: Optional[str] = None) -> bool:
        """Set leverage for a symbol."""
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Would set leverage to {leverage}x")
            return True

        if symbol is None:
            symbol = self._symbol_cache or config.SYMBOL
        
        body = {"product_id": symbol, "leverage": leverage}
        result = self._request("PUT", "/v2/positions/leverage", body)
        return result is not None

    def get_market_data(self) -> Dict:
        """Get current market data."""
        ticker = self.get_ticker()
        if not ticker:
            return {}

        result = ticker
        quotes = result.get("quotes", {})

        return {
            "last_price": float(result.get("close", 0)),
            "bid": float(quotes.get("best_bid", 0)),
            "ask": float(quotes.get("best_ask", 0)),
            "24h_high": float(result.get("high", 0)),
            "24h_low": float(result.get("low", 0)),
            "24h_volume": float(result.get("volume", 0)),
            "mark_price": float(result.get("mark_price", 0)),
            "index_price": float(result.get("spot_price", 0)),
            "funding_rate": float(result.get("funding_rate", 0))
        }

    def get_order_book(self, symbol: Optional[str] = None, depth: int = 20) -> Optional[Dict]:
        """Get order book data."""
        if symbol is None:
            symbol = self._symbol_cache or config.SYMBOL
        return self._public_request(f"{BASE_URL}/v2/orderbook?symbol={symbol}&depth={depth}")