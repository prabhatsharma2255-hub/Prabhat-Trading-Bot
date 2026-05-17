import time
import hmac
import hashlib
import json
import requests
from typing import Dict, List, Optional, Any
import config

BASE_URL = "https://api.india.delta.exchange"


class DeltaClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _generate_signature(self, method: str, path: str, body: str = "") -> Dict[str, str]:
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

    def _request(self, method: str, path: str, body: Dict = None, timeout: int = 10) -> Any:
        url = BASE_URL + path
        body_str = json.dumps(body) if body else ""
        headers = self._generate_signature(method, path, body_str)

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
            print(f"API Error: Request timed out")
            return None
        except Exception as e:
            print(f"API Error: {e}")
            return None

    def _public_request(self, method: str, path: str, timeout: int = 10) -> Any:
        url = BASE_URL + path
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Public API Error: {e}")
            return None

    def get_ticker(self, symbol: str = None) -> Optional[Dict]:
        if symbol is None:
            symbol = config.SYMBOL
        return self._public_request("GET", f"/v2/tickers/{symbol}")

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        end_time = int(time.time())
        start_time = end_time - (60 * 60 * 24)

        resolution_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        resolution = resolution_map.get(timeframe, "15m")

        data = self._public_request("GET", f"/v2/history/candles?symbol={symbol}&resolution={resolution}&start={start_time}&end={end_time}&limit={limit}", timeout=15)
        return data.get("result", []) if data else []

    def get_balance(self) -> float:
        data = self._request("GET", "/v2/wallet/balances")
        if data and "result" in data:
            for balance in data["result"]:
                if balance.get("asset_code") == "USD":
                    return float(balance.get("available_balance", 0))
        return 0.0

    def get_positions(self) -> List[Dict]:
        data = self._request("GET", "/v2/positions")
        return data.get("result", []) if data else []

    def get_open_orders(self) -> List[Dict]:
        data = self._request("GET", f"/v2/orders?product_id={config.SYMBOL}&state=open")
        return data.get("result", []) if data else []

    def place_order(self, order_type: str, side: str, size: float, price: Optional[float] = None,
                    stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                    leverage: int = 1) -> Optional[Dict]:

        if config.DRY_RUN:
            print(f"[DRY RUN] Would place order: {order_type} {side} {size} @ {price or 'market'}")
            return {"order_id": "dry_run_order", "state": "open"}

        order_params = {
            "product_id": config.SYMBOL,
            "size": size,
            "side": side,
            "order_type": order_type,
            "leverage": leverage
        }

        if price:
            order_params["price"] = str(price)
        if stop_loss:
            order_params["stop_loss"] = str(stop_loss)
        if take_profit:
            order_params["take_profit"] = str(take_profit)

        return self._request("POST", "/v2/orders", order_params)

    def cancel_order(self, order_id: str) -> bool:
        if config.DRY_RUN:
            print(f"[DRY RUN] Would cancel order: {order_id}")
            return True
        return self._request("DELETE", f"/v2/orders/{order_id}")

    def get_funding_rate(self, symbol: str = None) -> Optional[float]:
        if symbol is None:
            symbol = config.SYMBOL
        data = self._public_request("GET", f"/v2/tickers/{symbol}")
        if data and "result" in data:
            return float(data["result"].get("funding_rate", 0))
        return None

    def get_order_book(self, symbol: str = None, depth: int = 20) -> Optional[Dict]:
        if symbol is None:
            symbol = config.SYMBOL
        return self._public_request("GET", f"/v2/orderbook?symbol={symbol}&depth={depth}")

    def set_leverage(self, leverage: int, symbol: str = None) -> bool:
        if config.DRY_RUN:
            print(f"[DRY RUN] Would set leverage to {leverage}x")
            return True

        if symbol is None:
            symbol = config.SYMBOL
        body = {"product_id": symbol, "leverage": leverage}
        result = self._request("PUT", "/v2/positions/leverage", body)
        return result is not None

    def get_market_data(self) -> Dict:
        ticker = self.get_ticker()
        if not ticker:
            return {}

        result = ticker.get("result", {})
        quotes = result.get("quotes", {})

        return {
            "last_price": float(result.get("close", 0)),
            "bid": float(quotes.get("best_bid", 0)),
            "ask": float(quotes.get("best_ask", 0)),
            "24h_high": float(result.get("high", 0)),
            "24h_low": float(result.get("low", 0)),
            "24h_volume": float(result.get("volume", 0)),
            "mark_price": float(result.get("mark_price", 0)),
            "index_price": float(result.get("spot_price", 0))
        }