"""
Risk Manager - Production-grade risk management for small accounts

Philosophy: On $100 account with leverage, survival = edge accumulation.
Goal: Still be alive after 30 days so edge has time to compound.

Features:
- Percentage-based position sizing (grows/shrinks with account)
- Dynamic leverage based on trade grade and regime
- Drawdown tracking and automatic size reduction
- Daily limits (trades, drawdown, consecutive losses)
- Review mode for poor performance
- Take profit tiers with position management
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, date, time
import logging
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.current_balance = initial_capital
        self.peak_balance = initial_capital
        self.session_start_balance = initial_capital
        
        self.trades_today = 0
        self.consecutive_losses = 0
        self.last_reset_date = date.today()
        
        self.max_trades_per_day = config.MAX_TRADES_PER_DAY
        self.max_daily_drawdown = config.MAX_DAILY_DRAWDOWN_PCT
        self.max_consecutive_losses = config.MAX_CONSECUTIVE_LOSSES
        
        self.trade_history: List[Dict] = []
        self.open_positions: List[Dict] = []
        
        self.review_mode = False
        self.total_trades_count = 0
        self.winning_trades_count = 0
        
        self._init_database()

    def _init_database(self) -> None:
        """Initialize risk tracking database."""
        conn = sqlite3.connect("trades.db")
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS risk_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            balance REAL,
            peak_balance REAL,
            drawdown_pct REAL,
            trades_today INTEGER,
            consecutive_losses INTEGER,
            review_mode INTEGER,
            event_type TEXT,
            event_detail TEXT
        )''')
        
        conn.commit()
        conn.close()

    def reset_daily(self) -> None:
        """Reset daily counters if new day."""
        today = date.today()
        if today > self.last_reset_date:
            self.trades_today = 0
            self.last_reset_date = today
            logger.info("Daily counters reset")

    def update_balance(self, pnl: float) -> None:
        """Update balance after trade."""
        self.current_balance += pnl
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        self._check_drawdown()

    def _check_drawdown(self) -> None:
        """Check and handle drawdown scenarios."""
        if self.peak_balance > 0:
            drawdown_pct = (self.peak_balance - self.current_balance) / self.peak_balance
            
            if drawdown_pct > 0.10:
                logger.warning(f"CRITICAL DRAWDOWN: {drawdown_pct*100:.1f}% - STOPPING TRADING")
                self.review_mode = True
                self._log_event("drawdown_critical", f"Ddrawdown: {drawdown_pct*100:.1f}%")
            elif drawdown_pct > 0.05:
                logger.warning(f"Drawdown alert: {drawdown_pct*100:.1f}% - reducing sizes")
                self._log_event("drawdown_warning", f"DD: {drawdown_pct*100:.1f}%")

    def get_drawdown_pct(self) -> float:
        """Calculate current drawdown percentage."""
        if self.peak_balance > 0:
            return (self.peak_balance - self.current_balance) / self.peak_balance
        return 0.0

    def can_trade(self) -> Tuple[bool, str]:
        """Check if new trade is allowed."""
        self.reset_daily()
        
        if self.review_mode:
            return False, "REVIEW_MODE: Poor performance - dry run only"
        
        if self.trades_today >= self.max_trades_per_day:
            return False, "Max trades reached"
        
        session_drawdown = (self.session_start_balance - self.current_balance) / self.session_start_balance
        if session_drawdown >= self.max_daily_drawdown:
            return False, "Daily drawdown limit reached"
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning("Max consecutive losses reached - pausing")
            return False, "Max consecutive losses - pause"
        
        if len(self.open_positions) >= config.MAX_OPEN_POSITIONS:
            return False, "Max open positions"
        
        return True, "OK"

    def calculate_position_size(self, entry_price: float, stop_loss: float, 
                                 grade: str, regime: str) -> Tuple[float, float]:
        """
        Calculate position size based on trade grade and risk rules.
        
        Returns: (position_size, risk_amount)
        """
        risk_pct = {
            "grade_a": config.RISK_GRADE_A,
            "grade_b": config.RISK_GRADE_B,
            "grade_c": config.RISK_GRADE_C
        }.get(grade, config.RISK_GRADE_C)
        
        drawdown = self.get_drawdown_pct()
        if drawdown > 0.05:
            risk_pct *= 0.5
            logger.info(f"Position size reduced 50% due to drawdown")
        if drawdown > 0.10:
            return 0, 0
        
        risk_amount = self.current_balance * risk_pct
        
        if entry_price > 0 and stop_loss > 0:
            stop_distance = abs(entry_price - stop_loss)
            if stop_distance / entry_price > config.MAX_SL_DISTANCE_PCT:
                logger.warning(f"Stop loss too wide: {stop_distance/entry_price*100:.2f}% > {config.MAX_SL_DISTANCE_PCT*100}%")
                return 0, 0
            
            position_size = risk_amount / stop_distance
        else:
            position_size = risk_amount / entry_price
        
        position_size = max(position_size, 0.001)
        
        return float(position_size), float(risk_amount)

    def record_trade_open(self, trade: Dict) -> None:
        """Record a new open position."""
        self.open_positions.append({
            **trade,
            "opened_at": datetime.now().isoformat(),
            "tp1_hit": False,
            "tp2_hit": False,
            "sl_moved_to_breakeven": False
        })
        self.trades_today += 1

    def record_trade_close(self, pnl: float, reason: str, position_id: int) -> None:
        """Record trade closure."""
        if position_id < len(self.open_positions):
            closed = self.open_positions.pop(position_id)
            
            self.trade_history.append({
                **closed,
                "closed_at": datetime.now().isoformat(),
                "pnl": pnl,
                "close_reason": reason
            })
            
            self.total_trades_count += 1
            if pnl > 0:
                self.winning_trades_count += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
            
            self.update_balance(pnl)
            
            if self.total_trades_count >= config.REVIEW_MODE_MIN_TRADES:
                self._check_review_mode()

    def _check_review_mode(self) -> None:
        """Check if should enter review mode based on performance."""
        win_rate = self.winning_trades_count / self.total_trades_count
        
        avg_r = self._calculate_avg_r()
        
        if win_rate < config.REVIEW_MODE_MIN_WINRATE and avg_r < config.REVIEW_MODE_MIN_RR:
            self.review_mode = True
            logger.warning(f"ENTERING REVIEW MODE: Win rate {win_rate*100:.1f}% < {config.REVIEW_MODE_MIN_WINRATE*100}%, Avg R: {avg_r:.2f} < {config.REVIEW_MODE_MIN_RR}")
            self._log_event("review_mode_entered", f"WR: {win_rate*100:.1f}%, AvgR: {avg_r:.2f}")

    def _calculate_avg_r(self) -> float:
        """Calculate average risk-reward ratio of trades."""
        if not self.trade_history:
            return 0.0
        
        winning_trades = [t for t in self.trade_history if t.get("pnl", 0) > 0]
        losing_trades = [t for t in self.trade_history if t.get("pnl", 0) < 0]
        
        if not winning_trades or not losing_trades:
            return 0.0
        
        avg_win = sum(t["pnl"] for t in winning_trades) / len(winning_trades)
        avg_loss = abs(sum(t["pnl"] for t in losing_trades) / len(losing_trades))
        
        if avg_loss > 0:
            return avg_win / avg_loss
        return 0.0

    def check_position_management(self) -> List[Dict]:
        """
        Check open positions for take profit / stop loss management.
        Returns list of actions to take.
        """
        actions = []
        current_price = 0
        
        for i, pos in enumerate(self.open_positions):
            entry = pos.get("entry_price", 0)
            side = pos.get("side", "")
            direction = pos.get("direction", "")
            sl = pos.get("stop_loss", 0)
            tp1 = pos.get("take_profit_1", 0)
            tp2 = pos.get("take_profit_2", 0)
            risk_amount = pos.get("risk_amount", 0)
            
            pnl_pct = 0
            if direction == "LONG" and entry > 0:
                pnl_pct = (current_price - entry) / entry
            elif direction == "SHORT" and entry > 0:
                pnl_pct = (entry - current_price) / entry
            
            if sl > 0:
                if direction == "LONG" and current_price <= sl:
                    actions.append({"action": "stop_loss", "position_id": i})
                elif direction == "SHORT" and current_price >= sl:
                    actions.append({"action": "stop_loss", "position_id": i})
            
            if tp1 > 0 and not pos.get("tp1_hit"):
                if direction == "LONG" and current_price >= tp1:
                    actions.append({"action": "take_profit_1", "position_id": i, "close_pct": config.TP1_CLOSE_PCT})
                elif direction == "SHORT" and current_price <= tp1:
                    actions.append({"action": "take_profit_1", "position_id": i, "close_pct": config.TP1_CLOSE_PCT})
            
            if tp2 > 0 and not pos.get("tp2_hit"):
                if direction == "LONG" and current_price >= tp2:
                    actions.append({"action": "take_profit_2", "position_id": i, "close_pct": config.TP2_CLOSE_PCT})
                elif direction == "SHORT" and current_price <= tp2:
                    actions.append({"action": "take_profit_2", "position_id": i, "close_pct": config.TP2_CLOSE_PCT})
            
            if pos.get("tp1_hit") or pos.get("tp2_hit"):
                hours_open = (datetime.now() - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600
                if hours_open > 8 and pnl_pct > 0:
                    actions.append({"action": "time_exit", "position_id": i})

        return actions

    def get_stats(self) -> Dict:
        """Get current risk management statistics."""
        self.reset_daily()
        
        total_trades = len(self.trade_history)
        wins = len([t for t in self.trade_history if t.get("pnl", 0) > 0])
        
        return {
            "balance": self.current_balance,
            "peak_balance": self.peak_balance,
            "drawdown_pct": self.get_drawdown_pct() * 100,
            "session_drawdown_pct": ((self.session_start_balance - self.current_balance) / self.session_start_balance * 100) if self.session_start_balance > 0 else 0,
            "total_trades": total_trades,
            "winning_trades": wins,
            "losing_trades": total_trades - wins,
            "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0,
            "trades_today": self.trades_today,
            "consecutive_losses": self.consecutive_losses,
            "open_positions": len(self.open_positions),
            "review_mode": self.review_mode,
            "avg_r": self._calculate_avg_r()
        }

    def _log_event(self, event_type: str, event_detail: str) -> None:
        """Log risk management event to database."""
        conn = sqlite3.connect("trades.db")
        c = conn.cursor()
        c.execute('''INSERT INTO risk_tracking 
            (timestamp, balance, peak_balance, drawdown_pct, trades_today, consecutive_losses, review_mode, event_type, event_detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (datetime.now().isoformat(), self.current_balance, self.peak_balance, 
             self.get_drawdown_pct(), self.trades_today, self.consecutive_losses,
             1 if self.review_mode else 0, event_type, event_detail))
        conn.commit()
        conn.close()