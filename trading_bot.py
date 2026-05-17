"""
Trading Bot - Dual Mode Execution Engine

MODE 1: Conviction Trade (4-5/5 signals, full size)
MODE 2: Calculated Risk Trade (3/5 signals + price action, smaller size)
"""

import time
import logging
from datetime import datetime
from typing import Dict, Optional, List

import config
from delta_client import DeltaClient
from indicators import TechnicalIndicators
from ai_brain import AIBrain, TradeMode
from risk_manager import RiskManager
import dashboard

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self, api_key: str, api_secret: str):
        self.client = DeltaClient(api_key, api_secret)
        self.ai_brain = AIBrain()
        self.risk_manager = RiskManager(config.STARTING_CAPITAL)
        
        self.last_analysis_time = 0
        self.last_candle_time = 0
        self.is_running = False
        
        self.open_positions: List[Dict] = []
        
        self._run_connection_test()

    def _run_connection_test(self):
        """Test API connection on startup."""
        logger.info("=" * 60)
        logger.info("RUNNING CONNECTION TEST")
        logger.info("=" * 60)
        
        result = self.client.test_connection()
        
        logger.info(f"API Reachable:        {result.get('api_reachable', False)}")
        logger.info(f"Symbol Found:         {result.get('symbol_found', 'UNKNOWN')}")
        logger.info(f"Candles Retrieved:    {result.get('candles_retrieved', 0)}")
        logger.info(f"Last Candle Time:     {result.get('last_candle_time', 'N/A')}")
        
        if result.get('candles_retrieved', 0) == 0:
            logger.error("CRITICAL: No candles retrieved")

    def get_market_data(self, timeframe: str, limit: int) -> List[Dict]:
        """Fetch market data for a timeframe."""
        candles = self.client.get_candles(config.SYMBOL, timeframe, limit)
        return candles if candles else []

    def analyze_market(self) -> Optional[Dict]:
        """Run full market analysis with dual trade modes."""
        now = time.time()
        if now - self.last_analysis_time < config.POLLING_INTERVAL:
            return None

        logger.info(f"\n{'='*50}")
        logger.info(f"CYCLE {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*50}")

        # Reset daily counters
        self.ai_brain.reset_daily_counters()
        self.risk_manager.reset_daily()

        ltf_candles = self.get_market_data(config.TIMEFRAMES["entry"], config.LTF_CANDLES)
        
        if not ltf_candles:
            logger.warning("No LTF candles retrieved - skipping cycle")
            return None

        current_candle_time = ltf_candles[-1].get("time", 0)
        if current_candle_time == self.last_candle_time:
            logger.debug("No new candle")
        
        self.last_candle_time = current_candle_time

        try:
            ltf_indicators = TechnicalIndicators(ltf_candles).all_indicators()
        except Exception as e:
            logger.error(f"Error calculating LTF indicators: {e}")
            return None

        htf_indicators = None
        htf_candles = self.get_market_data(config.TIMEFRAMES["filter"], config.HTF_CANDLES)
        
        if htf_candles:
            try:
                htf_indicators = TechnicalIndicators(htf_candles).all_indicators()
            except Exception as e:
                logger.warning(f"HTF indicators failed: {e}")

        analysis = self.ai_brain.analyze(ltf_indicators, htf_indicators)
        
        can_trade, reason = self.risk_manager.can_trade(analysis.get("mode", 1))
        
        if can_trade and analysis.get("can_trade"):
            analysis["approved"] = True
            analysis["skip_reason"] = None
        else:
            analysis["approved"] = False
            analysis["skip_reason"] = reason or analysis.get("skip_reason")

        stats = self.risk_manager.get_stats()
        
        mode_str = analysis.get("trade_mode", "none")
        if mode_str == "mode1_conviction":
            mode_display = "MODE1"
        elif mode_str == "mode2_calculated":
            mode_display = "MODE2"
        else:
            mode_display = "NONE"
        
        logger.info(f"Balance: ${stats['balance']:.2f} | Peak: ${stats['peak_balance']:.2f} | DD: {stats['drawdown_pct']:.1f}%")
        logger.info(f"Regime: {analysis.get('regime', 'unknown')} | Session: {analysis.get('session', 'unknown')}")
        logger.info(f"Signals: {analysis.get('signals_count', 0)}/5 | Mode: {mode_display}")
        logger.info(f"Direction: {analysis.get('direction', 'NONE')} | HTF: {analysis.get('htf_status', 'N/A')}")
        
        if not analysis.get("approved"):
            logger.info(f"SKIPPED: {analysis.get('skip_reason', 'unknown')}")
        
        if stats.get("mode2_suspended"):
            logger.warning("*** MODE 2 SUSPENDED ***")
        
        logger.info(f"Open: {len(self.open_positions)} | Today: {stats['trades_today']}/{config.MAX_TRADES_DAY}")

        self.last_analysis_time = now
        
        analysis["ltf_indicators"] = ltf_indicators
        analysis["htf_indicators"] = htf_indicators
        
        return analysis

    def execute_trade(self, analysis: Dict) -> bool:
        """Execute a trade based on analysis."""
        if not analysis.get("approved"):
            return False

        direction = analysis.get("direction", "NONE")
        if direction == "NONE":
            return False

        price = analysis.get("current_price", 0)
        if price == 0:
            return False

        anti_chase_pct = config.ANTI_CHASE_PCT
        signal_candle_price = analysis.get("ltf_indicators", {}).get("current_price", price)
        
        if signal_candle_price > 0:
            price_move_pct = abs(price - signal_candle_price) / signal_candle_price
            if price_move_pct > anti_chase_pct:
                logger.warning(f"Price moved {price_move_pct*100:.2f}% since signal - SKIPPING")
                return False

        can_trade, reason = self.risk_manager.can_trade(analysis.get("mode", 1))
        if not can_trade:
            logger.warning(f"Cannot trade: {reason}")
            return False

        mode = analysis.get("mode", 1)
        regime = analysis.get("regime", "unknown")
        
        position_size, risk_amount = self.risk_manager.calculate_position_size(
            price,
            analysis.get("stop_loss", 0),
            mode,
            regime
        )

        if position_size <= 0:
            logger.warning("Position size calculated to 0")
            return False

        side = "buy" if direction == "LONG" else "sell"
        leverage = analysis.get("leverage", 1)

        mode_str = "MODE1" if mode == 1 else "MODE2"
        logger.info(f">>> EXECUTING: {mode_str} {direction} {position_size:.4f} @ ${price:.2f} (leverage: {leverage}x)")

        order = self.client.place_order(
            "market", side, position_size, None,
            analysis.get("stop_loss"),
            analysis.get("take_profit_2") if mode == 2 else analysis.get("take_profit_3"),
            leverage
        )

        if order:
            position = {
                "order_id": order.get("order_id", "unknown"),
                "direction": direction,
                "side": side,
                "entry_price": price,
                "size": position_size,
                "stop_loss": analysis.get("stop_loss", 0),
                "take_profit_1": analysis.get("take_profit_1", 0),
                "take_profit_2": analysis.get("take_profit_2", 0),
                "take_profit_3": analysis.get("take_profit_3", 0),
                "leverage": leverage,
                "risk_amount": risk_amount,
                "mode": mode,
                "regime": analysis.get("regime", "unknown"),
                "module": analysis.get("module", "unknown"),
                "signals_fired": analysis.get("signals_fired", []),
                "htf_aligned": analysis.get("htf_aligned", False),
                "session": analysis.get("session", "unknown"),
                "opened_at": datetime.now().isoformat()
            }
            
            self.open_positions.append(position)
            self.risk_manager.record_trade_open(position)
            
            dashboard.log_trade(
                direction=direction,
                entry_price=price,
                exit_price=0,
                size=position_size,
                pnl=0,
                status="open",
                confidence=analysis.get("signals_count", 0) * 20,
                regime=analysis.get("regime", "unknown"),
                signals=str(analysis.get("signals_fired", [])),
                htf_aligned=analysis.get("htf_aligned", False),
                session=analysis.get("session", "unknown"),
                grade=mode_str,
                module=analysis.get("module", "unknown")
            )
            
            logger.info(f"Trade executed: {mode_str}")
            return True

        logger.error("Order placement failed")
        return False

    def monitor_positions(self, current_price: float):
        """Monitor open positions for TP/SL management."""
        positions_to_close = []
        
        for i, pos in enumerate(self.open_positions):
            entry = pos.get("entry_price", 0)
            direction = pos.get("direction", "")
            mode = pos.get("mode", 1)
            sl = pos.get("stop_loss", 0)
            tp1 = pos.get("take_profit_1", 0)
            tp2 = pos.get("take_profit_2", 0)
            risk_amount = pos.get("risk_amount", 0)
            
            pnl = 0
            if direction == "LONG" and entry > 0:
                pnl = (current_price - entry) * pos.get("size", 0)
            elif direction == "SHORT" and entry > 0:
                pnl = (entry - current_price) * pos.get("size", 0)
            
            if direction == "LONG":
                if sl > 0 and current_price <= sl:
                    logger.info(f"STOP LOSS: {direction} at ${current_price:.2f}")
                    positions_to_close.append((i, pnl, "SL", mode))
                    
                elif tp1 > 0 and current_price >= tp1 and not pos.get("tp1_hit"):
                    logger.info(f"TP1 HIT: Closing 50% at ${current_price:.2f}")
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    
                elif tp2 > 0 and current_price >= tp2 and not pos.get("tp2_hit"):
                    logger.info(f"TP2 HIT: Closing remaining at ${current_price:.2f}")
                    positions_to_close.append((i, pnl, "TP2", mode))
                    
            elif direction == "SHORT":
                if sl > 0 and current_price >= sl:
                    logger.info(f"STOP LOSS: {direction} at ${current_price:.2f}")
                    positions_to_close.append((i, pnl, "SL", mode))
                    
                elif tp1 > 0 and current_price <= tp1 and not pos.get("tp1_hit"):
                    logger.info(f"TP1 HIT: Closing 50% at ${current_price:.2f}")
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    
                elif tp2 > 0 and current_price <= tp2 and not pos.get("tp2_hit"):
                    logger.info(f"TP2 HIT: Closing remaining at ${current_price:.2f}")
                    positions_to_close.append((i, pnl, "TP2", mode))

        for idx, pnl, reason, mode in reversed(positions_to_close):
            if idx < len(self.open_positions):
                pos = self.open_positions[idx]
                self.risk_manager.record_trade_close(pnl, reason, idx, mode)
                
                # Record for pattern memory
                self.ai_brain.record_closed_trade(
                    pnl, reason, pos.get("regime", "unknown"),
                    pos.get("session", "unknown"), mode,
                    pos.get("signals_count", 0), pos.get("direction", "")
                )
                
                dashboard.log_trade(
                    direction=pos.get("direction", ""),
                    entry_price=pos.get("entry_price", 0),
                    exit_price=pnl,
                    size=pos.get("size", 0),
                    pnl=pnl,
                    status="closed",
                    confidence=0,
                    regime=pos.get("regime", "unknown"),
                    outcome=reason
                )

    def run(self) -> None:
        """Main trading loop."""
        self.is_running = True
        
        logger.info("=" * 60)
        logger.info("DELTA EXCHANGE AI TRADING BOT - DUAL MODE")
        logger.info(f"Starting Capital: ${config.STARTING_CAPITAL}")
        logger.info(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
        logger.info(f"Max Trades/Day: {config.MAX_TRADES_DAY}")
        logger.info(f"Mode 1 (Conviction): {config.MIN_SIGNALS_MODE1}+ signals")
        logger.info(f"Mode 2 (Risk): {config.MIN_SIGNALS_MODE2}+ signals + price action")
        logger.info("=" * 60)

        while self.is_running:
            try:
                analysis = self.analyze_market()
                
                if analysis and analysis.get("approved"):
                    self.execute_trade(analysis)

                market_data = self.client.get_market_data()
                if market_data:
                    current_price = market_data.get("last_price", 0)
                    if current_price > 0 and self.open_positions:
                        self.monitor_positions(current_price)

                stats = self.risk_manager.get_stats()
                logger.info(f"Stats: {stats['total_trades']} total, Today: {stats['trades_today']}, WR: {stats['win_rate']:.0f}%")

            except KeyboardInterrupt:
                logger.info("Stopping bot...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                import traceback
                traceback.print_exc()

            time.sleep(config.POLLING_INTERVAL)

    def stop(self):
        """Stop the trading bot."""
        self.is_running = False