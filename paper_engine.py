"""
PaperEngine - Simulated paper trading engine
Wraps DeltaClient to simulate fills, slippage, fees, and balance tracking
"""

import time
import logging
import copy
import json
import os
import csv
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock

import config
from delta_client import DeltaClient

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

PAPER_LOG_FILE = "paper_trades.csv"
PAPER_STATE_FILE = "paper_state.json"


class PaperEngine:
    """Simulated trading engine. Drop-in for DeltaClient in DRY_RUN mode.

    All data methods (get_candles, get_ticker, get_market_data, etc.)
    delegate to the real DeltaClient. Only trading methods are simulated.
    """

    def __init__(self, api_key: str, api_secret: str, initial_balance: float = 100.0):
        self._real = DeltaClient(api_key, api_secret)
        self._lock = Lock()

        self.initial_balance = initial_balance
        self.balance = initial_balance
        self._equity = initial_balance

        self._positions: List[Dict] = []
        self._orders: List[Dict] = []
        self._closed_trades: List[Dict] = []
        self._trade_counter: int = 0

        self.slippage_pct = 0.05
        self.taker_fee_pct = 0.05
        self.maker_fee_pct = 0.02

        self._load_state()

        logger.info(f"PaperEngine initialized | Balance: ${self.balance:.2f} | "
                     f"Slippage: {self.slippage_pct}% | Taker Fee: {self.taker_fee_pct}%")

    # ---- Persistence ----

    def _state_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), PAPER_STATE_FILE)

    def _log_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), PAPER_LOG_FILE)

    def _save_state(self):
        with self._lock:
            state = {
                "initial_balance": self.initial_balance,
                "balance": self.balance,
                "equity": self._equity,
                "trade_counter": self._trade_counter,
                "updated": str(now_ist())
            }
            try:
                with open(self._state_path(), "w") as f:
                    json.dump(state, f)
            except:
                pass

    def _load_state(self):
        try:
            with open(self._state_path()) as f:
                state = json.load(f)
            self.initial_balance = state.get("initial_balance", self.initial_balance)
            self.balance = state.get("balance", self.initial_balance)
            self._equity = state.get("equity", self.balance)
            self._trade_counter = state.get("trade_counter", 0)
            logger.info(f"PaperEngine state restored: balance=${self.balance:.2f}")
        except:
            pass

    def _log_trade(self, trade: Dict):
        path = self._log_path()
        file_exists = os.path.exists(path)
        try:
            with open(path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=trade.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade)
        except:
            pass

    # ---- Slippage simulation ----

    def _apply_slippage(self, price: float, side: str) -> float:
        sign = 1 if side == "buy" else -1
        return price * (1 + sign * self.slippage_pct / 100)

    def _calc_fee(self, value: float, is_taker: bool = True) -> float:
        pct = self.taker_fee_pct if is_taker else self.maker_fee_pct
        return value * pct / 100

    def _next_trade_id(self) -> str:
        self._trade_counter += 1
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"paper_{ts}_{self._trade_counter:04d}"

    def _current_mark_price(self) -> float:
        md = self._real.get_market_data()
        return md.get("mark_price", 0) or md.get("last_price", 0)

    # ---- DeltaClient passthrough methods ----

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict]:
        return self._real.get_candles(symbol, timeframe, limit)

    def get_ticker(self, symbol: Optional[str] = None) -> Optional[Dict]:
        return self._real.get_ticker(symbol)

    def get_market_data(self) -> Dict:
        return self._real.get_market_data()

    def get_order_book(self, symbol: Optional[str] = None, depth: int = 20) -> Optional[Dict]:
        return self._real.get_order_book(symbol, depth)

    def test_connection(self) -> Dict[str, Any]:
        result = self._real.test_connection()
        result["dry_run"] = True
        return result

    def _public_request(self, url: str, timeout: int = 10) -> Any:
        return self._real._public_request(url, timeout)

    # ---- Simulated trading methods ----

    def place_order(self, order_type: str, side: str, size: float,
                    price: Optional[float] = None,
                    stop_loss: Optional[float] = None,
                    take_profit: Optional[float] = None,
                    leverage: int = 1) -> Optional[Dict]:
        with self._lock:
            mark = self._current_mark_price()
            if mark == 0:
                logger.warning("[PaperEngine] No market price available")
                return None

            fill_price = mark if price is None else price
            fill_price = self._apply_slippage(fill_price, side)

            order_value = abs(size) * fill_price
            fee = self._calc_fee(order_value, is_taker=(order_type == "market"))
            margin_required = order_value / leverage

            if margin_required > self.balance:
                logger.warning(f"[PaperEngine] Insufficient balance: need ${margin_required:.2f}, have ${self.balance:.2f}")
                return None

            self.balance -= margin_required

            order_id = self._next_trade_id()
            now_str = str(now_ist())

            position = {
                "order_id": order_id,
                "symbol": "BTCUSD",
                "side": side,
                "direction": "LONG" if side == "buy" else "SHORT",
                "size": size,
                "entry_price": fill_price,
                "leverage": leverage,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "margin": margin_required,
                "fee": fee,
                "open_time": now_str,
                "state": "open"
            }

            self._positions.append(position)

            logger.info(f"[PaperEngine] FILLED {order_type} {side} {size:.4f} @ ${fill_price:.2f} "
                         f"| SL: {stop_loss} | TP: {take_profit} | Lev: {leverage}x | Fee: ${fee:.4f}")

            self._save_state()

            return {
                "order_id": order_id,
                "state": "open",
                "dry_run": True,
                "fill_price": fill_price,
                "fee": fee
            }

    def close_position(self, direction: str, size: float) -> Optional[Dict]:
        with self._lock:
            idx = None
            for i, p in enumerate(self._positions):
                if p["direction"] == direction and p["state"] == "open":
                    if abs(p["size"] - size) < 0.0001 or size >= p["size"]:
                        idx = i
                        break

            if idx is None:
                logger.warning(f"[PaperEngine] No open position to close: {direction} {size}")
                return None

            pos = self._positions.pop(idx)
            mark = self._current_mark_price()
            if mark == 0:
                logger.warning("[PaperEngine] No market price for close")
                return None

            close_price = self._apply_slippage(mark, "sell" if direction == "LONG" else "buy")
            close_value = size * close_price
            close_fee = self._calc_fee(close_value)

            if direction == "LONG":
                pnl = (close_price - pos["entry_price"]) * size * pos["leverage"]
            else:
                pnl = (pos["entry_price"] - close_price) * size * pos["leverage"]

            net_pnl = pnl - pos.get("fee", 0) - close_fee

            self.balance += pos.get("margin", 0) + net_pnl
            self._equity = self.balance

            now_str = str(now_ist())

            closed = {
                "id": pos["order_id"],
                "direction": direction,
                "entry_price": pos["entry_price"],
                "close_price": close_price,
                "size": size,
                "leverage": pos["leverage"],
                "pnl": round(net_pnl, 2),
                "pnl_pct": round((net_pnl / pos.get("margin", 1)) * 100, 2) if pos.get("margin", 0) > 0 else 0,
                "fee": round(pos.get("fee", 0) + close_fee, 4),
                "open_time": pos.get("open_time", ""),
                "close_time": now_str,
                "close_reason": "paper_close"
            }

            self._closed_trades.append(closed)
            self._log_trade(closed)
            self._save_state()

            logger.info(f"[PaperEngine] CLOSED {direction} | Entry: ${pos['entry_price']:.2f} "
                         f"| Exit: ${close_price:.2f} | PnL: ${net_pnl:.2f} ({closed['pnl_pct']}%)")

            return {"order_id": pos["order_id"], "state": "closed", "dry_run": True, "pnl": net_pnl}

    def set_leverage(self, leverage: int, symbol: Optional[str] = None) -> bool:
        logger.info(f"[PaperEngine] Leverage set to {leverage}x")
        return True

    def get_balance(self) -> float:
        with self._lock:
            return self.balance

    def get_positions(self) -> List[Dict]:
        with self._lock:
            return copy.deepcopy(self._positions)

    def get_open_orders(self) -> List[Dict]:
        with self._lock:
            return copy.deepcopy(self._orders)

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            initial = len(self._orders)
            self._orders = [o for o in self._orders if o.get("order_id") != order_id]
            cancelled = len(self._orders) < initial
            if cancelled:
                logger.info(f"[PaperEngine] Cancelled order: {order_id}")
            return cancelled

    def get_equity(self) -> float:
        with self._lock:
            unrealized = 0
            mark = self._current_mark_price()
            if mark > 0:
                for p in self._positions:
                    if p["state"] == "open":
                        if p["direction"] == "LONG":
                            unrealized += (mark - p["entry_price"]) * p["size"] * p["leverage"]
                        else:
                            unrealized += (p["entry_price"] - mark) * p["size"] * p["leverage"]
            return self.balance + unrealized

    def get_stats(self) -> Dict:
        with self._lock:
            wins = sum(1 for t in self._closed_trades if t.get("pnl", 0) > 0)
            losses = sum(1 for t in self._closed_trades if t.get("pnl", 0) <= 0)
            total_pnl = sum(t.get("pnl", 0) for t in self._closed_trades)
            total_fees = sum(t.get("fee", 0) for t in self._closed_trades)
            return {
                "initial_balance": self.initial_balance,
                "current_balance": round(self.balance, 2),
                "equity": round(self.get_equity(), 2),
                "total_pnl": round(total_pnl, 2),
                "total_fees": round(total_fees, 4),
                "total_trades": len(self._closed_trades),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
                "open_positions": len(self._positions),
                "return_pct": round((self.balance - self.initial_balance) / self.initial_balance * 100, 2)
            }

    def reset(self, initial_balance: Optional[float] = None):
        with self._lock:
            if initial_balance:
                self.initial_balance = initial_balance
            self.balance = self.initial_balance
            self._equity = self.initial_balance
            self._positions.clear()
            self._orders.clear()
            self._closed_trades.clear()
            self._trade_counter = 0
            self._save_state()
            logger.info(f"[PaperEngine] Reset to ${self.initial_balance:.2f}")
