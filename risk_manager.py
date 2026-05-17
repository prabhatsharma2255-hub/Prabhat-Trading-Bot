"""
Risk Manager - Dual Mode Trade Management

MODE 1: Conviction Trade (3% risk for Grade A, 2% for Grade B)
MODE 2: Calculated Risk Trade (1.5% default, 1% reduced, 2% boosted)

Features:
- Mode-specific position sizing
- Mode 2 suspension after consecutive losses
- Daily drawdown tracking (7%)
- Pattern memory integration
"""

import sqlite3
from typing import Dict, Tuple
from datetime import datetime, date
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
        
        self.max_trades_per_day = config.MAX_TRADES_DAY
        self.max_daily_drawdown = config.MAX_DAILY_DD_PCT
        
        self.trade_history = []
        self.open_positions = []
        
        self.review_mode = False
        self.total_trades_count = 0
        self.winning_trades_count = 0
        
        self.mode2_suspended = False
        
        self._init_database()

    def _init_database(self):
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
            mode2_suspended INTEGER,
            event_type TEXT,
            event_detail TEXT
        )''')
        
        conn.commit()
        conn.close()

    def reset_daily(self):
        """Reset daily counters if new day."""
        today = date.today()
        if today > self.last_reset_date:
            self.trades_today = 0
            self.consecutive_losses = 0
            self.mode2_suspended = False
            self.last_reset_date = today
            logger.info("Daily counters reset")

    def update_balance(self, pnl: float):
        """Update balance after trade."""
        self.current_balance += pnl
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

    def get_drawdown_pct(self) -> float:
        """Calculate current drawdown percentage."""
        if self.peak_balance > 0:
            return (self.peak_balance - self.current_balance) / self.peak_balance
        return 0.0

    def can_trade(self, mode: int = 1) -> Tuple[bool, str]:
        """Check if new trade is allowed."""
        self.reset_daily()
        
        if self.review_mode:
            return False, "REVIEW_MODE: Poor performance"
        
        session_drawdown = (self.session_start_balance - self.current_balance) / self.session_start_balance
        if session_drawdown >= self.max_daily_drawdown:
            return False, "Daily drawdown limit reached"
        
        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            return False, "Max consecutive losses - pause"
        
        if len(self.open_positions) >= config.MAX_OPEN_POSITIONS:
            return False, "Max open positions"
        
        # Mode 2 specific check
        if mode == 2 and self.mode2_suspended:
            return False, "Mode 2 suspended after 3 losses"
        
        if self.trades_today >= self.max_trades_per_day:
            return False, "Max trades reached"
        
        return True, "OK"

    def calculate_position_size(self, entry_price: float, stop_loss: float,
                                 mode: int, regime: str) -> Tuple[float, float]:
        """
        Calculate position size based on trade mode.
        
        Mode 1: Risk based on grade (3%, 2%, 1%)
        Mode 2: Risk 1.5% default, can be reduced to 1% or boosted to 2%
        """
        if mode == 1:
            risk_pct = config.RISK_MODE1_GRADE_A
        elif mode == 2:
            # Mode 2 sizing is handled in ai_brain based on pattern memory
            risk_pct = config.RISK_MODE2_DEFAULT
        else:
            risk_pct = 0.01
        
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
                logger.warning(f"Stop loss too wide: {stop_distance/entry_price*100:.2f}%")
                return 0, 0
            
            position_size = risk_amount / stop_distance
        else:
            position_size = risk_amount / entry_price
        
        position_size = max(position_size, 0.001)
        
        return float(position_size), float(risk_amount)

    def record_trade_open(self, trade: Dict):
        """Record a new open position."""
        self.open_positions.append({
            **trade,
            "opened_at": datetime.now().isoformat(),
            "tp1_hit": False,
            "tp2_hit": False,
            "sl_moved_to_breakeven": False
        })
        self.trades_today += 1

    def record_trade_close(self, pnl: float, reason: str, position_id: int, mode: int):
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
                
                # Mode 2 suspension check
                if mode == 2 and self.consecutive_losses >= config.MODE2_SUSPEND_CONSEC_LOSSES:
                    self.mode2_suspended = True
                    logger.warning(f"Mode 2 SUSPENDED after {config.MODE2_SUSPEND_CONSEC_LOSSES} consecutive losses")
            
            self.update_balance(pnl)

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
            "mode2_suspended": self.mode2_suspended
        }