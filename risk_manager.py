from typing import Dict, List, Tuple
from datetime import datetime
import config


class RiskManager:
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_daily_loss = initial_capital * 0.10
        self.trades_today = 0
        self.daily_pnl = 0
        self.last_reset = datetime.now()
        self.trade_history: List[Dict] = []
        self.max_trades_per_day = 10

    def reset_daily(self):
        if datetime.now().date() > self.last_reset.date():
            self.trades_today = 0
            self.daily_pnl = 0
            self.last_reset = datetime.now()

    def can_trade(self) -> Tuple[bool, str]:
        self.reset_daily()
        if self.trades_today >= self.max_trades_per_day:
            return False, "Max trades reached"
        if abs(self.daily_pnl) >= self.max_daily_loss:
            return False, "Daily loss limit reached"
        return True, "OK"

    def calculate_position_size(self, price: float, stop_loss: float, risk_amount: float) -> float:
        if stop_loss == 0 or price == 0:
            return 0.001
        risk_per_unit = abs(price - stop_loss)
        if risk_per_unit == 0:
            return 0.001
        position_size = risk_amount / risk_per_unit
        return max(position_size, 0.001)

    def record_trade(self, trade: Dict):
        self.trade_history.append({**trade, "timestamp": datetime.now().isoformat()})
        self.trades_today += 1
        self.daily_pnl += trade.get("pnl", 0)

    def get_stats(self) -> Dict:
        total = len(self.trade_history)
        wins = len([t for t in self.trade_history if t.get("pnl", 0) > 0])
        return {
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": total - wins,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "total_pnl": sum(t.get("pnl", 0) for t in self.trade_history),
            "trades_today": self.trades_today,
            "daily_pnl": self.daily_pnl
        }