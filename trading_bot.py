"""
Trading Bot - Setup-Based Execution Engine

Works with 12 named setups + News Intelligence + Move Detection
"""

import time
import logging
from datetime import datetime
from typing import Dict, Optional, List

import config
from delta_client import DeltaClient
from indicators import Indicators
from ai_brain import AIBrain
import dashboard

try:
    from news_engine import NewsEngine
except ImportError:
    NewsEngine = None

try:
    from move_detector import MoveDetector
except ImportError:
    MoveDetector = None

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
        
        self.news_engine = None
        self.move_detector = None
        
        if NewsEngine:
            try:
                self.news_engine = NewsEngine()
                self.news_engine.warm_up()
                logger.info("News Engine initialized and warmed up")
            except Exception as e:
                logger.warning(f"News Engine init failed: {e}")
        
        self.ai_brain = AIBrain(news_engine=self.news_engine)
        
        self.last_analysis_time = 0
        self.open_positions = []
        self.balance = config.STARTING_CAPITAL
        
        if MoveDetector:
            try:
                self.move_detector = MoveDetector(self.client)
                self.move_detector.start()
                logger.info("Move Detector started")
            except Exception as e:
                logger.warning(f"Move Detector init failed: {e}")
        
        self._run_connection_test()
        
        if not config.DRY_RUN:
            self._sync_positions()
    
    def _sync_positions(self):
        """Sync local positions with exchange."""
        try:
            exchange_positions = self.client.get_positions()
            self.open_positions = []
            
            for pos in exchange_positions:
                size = float(pos.get("size", 0))
                if size <= 0:
                    continue
                
                direction = "LONG" if pos.get("side") == "buy" else "SHORT"
                entry_price = float(pos.get("avg_price", 0))
                
                self.open_positions.append({
                    "direction": direction,
                    "entry_price": entry_price,
                    "size": abs(size),
                    "stop_loss": 0,
                    "take_profit_1": 0,
                    "take_profit_2": 0,
                    "leverage": 1,
                    "setup": "synced",
                    "risk_amount": 0,
                    "opened_at": pos.get("created_at", ""),
                    "tp1_hit": False,
                    "tp2_hit": False
                })
            
            logger.info(f"Synced {len(self.open_positions)} positions from exchange")
        except Exception as e:
            logger.warning(f"Position sync failed: {e}")
    
    def get_market_intelligence(self) -> Dict:
        intel = {
            "sentiment": "neutral",
            "composite": 0,
            "fear_greed": 50,
            "fear_greed_trend": "flat",
            "funding_rate": 0,
            "funding_bias": "neutral",
            "velocity_1m": 0,
            "velocity_3m": 0,
            "whale_event": "none",
            "urgent_event": False
        }
        
        if self.news_engine:
            sentiment = self.news_engine.get_composite_sentiment()
            intel["sentiment"] = sentiment.get("sentiment_label", "neutral")
            intel["composite"] = sentiment.get("composite", 0)
            intel["fear_greed"] = sentiment.get("fear_greed", 50)
            intel["urgent_event"] = sentiment.get("urgent_event", False)
            intel["top_headlines"] = sentiment.get("top_headlines", [])
        
        if self.move_detector:
            move_intel = self.move_detector.get_market_intelligence()
            intel["velocity_1m"] = move_intel.get("velocity_1m", 0)
            intel["velocity_3m"] = move_intel.get("velocity_3m", 0)
            intel["funding_rate"] = move_intel.get("funding_rate", 0)
            intel["funding_bias"] = move_intel.get("funding_bias", "neutral")
        
        if self.news_engine:
            if self.news_engine.whale_event_bull:
                intel["whale_event"] = "bull"
            elif self.news_engine.whale_event_bear:
                intel["whale_event"] = "bear"
        
        return intel
    
    def check_urgent_event(self) -> bool:
        if self.news_engine and self.news_engine.urgent_event:
            logger.warning(f"URGENT EVENT DETECTED: closing positions")
            return True
        return False
    
    def _run_connection_test(self):
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
        candles = self.client.get_candles(config.SYMBOL, timeframe, limit)
        return candles if candles else []
    
    def analyze_market(self) -> Optional[Dict]:
        now = time.time()
        if now - self.last_analysis_time < config.POLLING_INTERVAL:
            return None
        
        logger.info(f"\n{'='*50}")
        logger.info(f"CYCLE {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info(f"Balance: ${self.balance:.2f}")
        logger.info(f"{'='*50}")
        
        ltf_candles = self.get_market_data(config.TIMEFRAMES["entry"], config.LTF_CANDLES)
        
        if not ltf_candles:
            logger.warning("No candles retrieved")
            return None
        
        htf_candles = self.get_market_data(config.TIMEFRAMES["filter"], config.HTF_CANDLES)
        
        # Calculate velocity data for aggressive setups
        velocity_data = self._calculate_velocity(ltf_candles)
        
        # Pass news_engine and move_detector for aggressive setups
        analysis = self.ai_brain.analyze(
            ltf_candles, 
            htf_candles if htf_candles else None, 
            velocity_data,
            self.news_engine,
            self.move_detector
        )
        
        state = analysis["state"]
        
        logger.info(f"MARKET STATE")
        logger.info(f"BTC Price: ${state.current_price:.2f} | ATR: ${state.atr:.2f} ({state.atr/state.current_price*100:.2f}%)")
        logger.info(f"Structure: {state.structure.upper()}")
        logger.info(f"RSI: {state.rsi:.1f} | Divergence: {state.rsi_divergence}")
        logger.info(f"MACD: {state.macd_state} | Cross: {state.macd_cross_dir}")
        logger.info(f"VWAP Zone: {state.vwap_zone} | Event: {state.vwap_event}")
        logger.info(f"Volume: {state.rvol:.1f}x ({state.rvol_category})")
        logger.info(f"Squeeze: {'ON' if state.squeeze_on else 'OFF'} ({state.squeeze_bars} bars) | Fired: {state.squeeze_fired}")
        logger.info(f"Liq Sweep: {'bull' if state.liq_sweep_bull else 'bear' if state.liq_sweep_bear else 'none'}")
        logger.info(f"Pattern: {state.pattern} | Fib: {state.which_fib if state.which_fib else 'none'}")
        
        # Velocity info
        if velocity_data:
            logger.info(f"VELOCITY: 1m={velocity_data.get('velocity_1m', 0)*100:.2f}% | 3m={velocity_data.get('velocity_3m', 0)*100:.2f}%")
        
        logger.info(f"SETUP SCAN (12 SETUPS)")
        for i, setup in enumerate(analysis["all_setups"], 1):
            status = "TRIGGERED" if setup.triggered else "skipped"
            direction = f"→ {setup.direction}" if setup.triggered else ""
            logger.info(f"[{i:2d}] {setup.setup_name}: {status} {direction}")
        
        logger.info(f"HTF Bias: {'BULLISH' if state.htf_bullish else 'NEUTRAL'}")
        logger.info(f"Session: {analysis['session']}")
        
        if analysis["can_trade"] and analysis["setup"]:
            setup = analysis["setup"]
            logger.info(f"DECISION: {setup.direction} at ${state.current_price:.2f}")
            logger.info(f"Setup: {setup.setup_name}")
            logger.info(f"SL: ${setup.stop_loss:.2f} | TP1: ${setup.tp1:.2f} | TP2: ${setup.tp2:.2f}")
            logger.info(f"Risk: {setup.risk_pct*100}% | Leverage: {setup.leverage}x")
        else:
            reason = analysis.get("skip_reason", "no_setup")
            logger.info(f"DECISION: NO TRADE - {reason}")
        
        logger.info(f"Open Positions: {len(self.open_positions)}")
        
        self.last_analysis_time = now
        
        return analysis

    def _calculate_velocity(self, candles: List[Dict]) -> Dict:
        if len(candles) < 10:
            return {"velocity_1m": 0, "velocity_3m": 0}
        
        prices = [c.get("close", 0) for c in candles]
        
        if len(prices) >= 3:
            vel_1m = (prices[-1] - prices[-3]) / prices[-3]
        else:
            vel_1m = 0
        
        if len(prices) >= 7:
            vel_3m = (prices[-1] - prices[-7]) / prices[-7]
        else:
            vel_3m = 0
        
        return {"velocity_1m": vel_1m, "velocity_3m": vel_3m}
    
    def execute_trade(self, analysis: Dict) -> bool:
        if not analysis.get("can_trade") or not analysis.get("setup"):
            return False
        
        if len(self.open_positions) >= config.MAX_OPEN_POSITIONS:
            logger.warning(f"Max open positions reached: {config.MAX_OPEN_POSITIONS}")
            return False
        
        setup = analysis["setup"]
        
        for pos in self.open_positions:
            if pos.get("setup") == setup.setup_name:
                logger.warning(f"Setup {setup.setup_name} already open - blocking")
                return False
        
        state = analysis["state"]
        
        can_trade, reason = self.ai_brain.can_trade()
        if not can_trade:
            logger.warning(f"Cannot trade: {reason}")
            return False
        
        price = state.current_price
        direction = setup.direction
        
        risk_amount = self.balance * setup.risk_pct
        
        if price > 0 and setup.stop_loss > 0:
            stop_distance = abs(price - setup.stop_loss)
            if stop_distance > 0:
                position_size = risk_amount / stop_distance
            else:
                position_size = risk_amount / price
        else:
            return False
        
        if position_size * price * setup.leverage < config.MIN_POSITION_USD:
            logger.warning(f"Position too small: ${position_size * price * setup.leverage}")
            return False
        
        side = "buy" if direction == "LONG" else "sell"
        
        logger.info(f">>> EXECUTING: {setup.setup_name} {direction} {position_size:.4f} @ ${price:.2f}")
        
        order = self.client.place_order(
            "market", side, position_size, None,
            setup.stop_loss,
            setup.tp2,
            setup.leverage
        )
        
        if order:
            position = {
                "direction": direction,
                "entry_price": price,
                "size": position_size,
                "stop_loss": setup.stop_loss,
                "take_profit_1": setup.tp1,
                "take_profit_2": setup.tp2,
                "leverage": setup.leverage,
                "setup": setup.setup_name,
                "risk_amount": risk_amount,
                "opened_at": datetime.now().isoformat(),
                "tp1_hit": False,
                "tp2_hit": False
            }
            
            self.open_positions.append(position)
            
            dashboard.log_trade(
                direction=direction,
                entry_price=price,
                exit_price=0,
                size=position_size,
                pnl=0,
                status="open",
                confidence=80,
                regime=state.structure,
                signals=setup.setup_name,
                htf_aligned=state.htf_bullish,
                session=analysis["session"],
                grade=setup.setup_name,
                module=setup.setup_name,
                leverage=setup.leverage
            )
            
            logger.info("Trade executed successfully")
            return True
        
        logger.error("Order placement failed")
        return False
    
    def monitor_positions(self, current_price: float):
        to_close = []
        
        logger.info(f"MONITOR: Price=${current_price}, Open positions={len(self.open_positions)}")
        
        for i, pos in enumerate(self.open_positions):
            entry = pos["entry_price"]
            direction = pos["direction"]
            sl = pos["stop_loss"]
            tp1 = pos["take_profit_1"]
            tp2 = pos["take_profit_2"]
            
            logger.info(f"  Pos {i}: {direction} Entry=${entry} SL={sl} TP1={tp1} TP2={tp2}")
            
            leverage = pos.get("leverage", 1)
            pnl = 0
            if direction == "LONG":
                pnl = (current_price - entry) * pos["size"] * leverage
                if current_price <= sl:
                    to_close.append((i, pnl, "SL"))
                elif tp1 > 0 and current_price >= tp1 and not pos.get("tp1_hit"):
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    logger.info(f"TP1 HIT - SL moved to breakeven")
                elif tp2 > 0 and current_price >= tp2 and not pos.get("tp2_hit"):
                    to_close.append((i, pnl, "TP2"))
            else:
                pnl = (entry - current_price) * pos["size"] * leverage
                if current_price >= sl:
                    to_close.append((i, pnl, "SL"))
                elif tp1 > 0 and current_price <= tp1 and not pos.get("tp1_hit"):
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    logger.info(f"TP1 HIT - SL moved to breakeven")
                elif tp2 > 0 and current_price <= tp2 and not pos.get("tp2_hit"):
                    to_close.append((i, pnl, "TP2"))
        
        for idx, pnl, reason in reversed(to_close):
            if idx < len(self.open_positions):
                pos = self.open_positions.pop(idx)
                
                logger.info(f"CLOSING: {pos['direction']} Entry={pos['entry_price']} Exit={current_price} PnL=${pnl}")
                
                close_result = self.client.close_position(pos["direction"], pos["size"])
                
                self.balance += pnl
                
                if pnl > 0:
                    self.ai_brain.consecutive_losses = 0
                else:
                    self.ai_brain.consecutive_losses += 1
                
                dashboard.log_trade(
                    direction=pos["direction"],
                    entry_price=pos["entry_price"],
                    exit_price=current_price,
                    size=pos["size"],
                    pnl=pnl,
                    status="closed",
                    confidence=0,
                    regime="",
                    outcome=reason
                )
                
                logger.info(f"Trade closed: {reason} | PnL: ${pnl:.2f} | Exit: ${current_price}")
    
    def run(self):
        self.ai_brain.reset_daily()
        
        logger.info("=" * 60)
        logger.info("DELTA EXCHANGE AI TRADING BOT - SETUP BASED")
        logger.info(f"Starting Capital: ${config.STARTING_CAPITAL}")
        logger.info(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
        logger.info(f"Max Trades/Day: {config.MAX_TRADES_PER_DAY}")
        logger.info("=" * 60)
        
        while True:
            try:
                analysis = self.analyze_market()
                
                if analysis and analysis.get("can_trade"):
                    self.execute_trade(analysis)
                
                market_data = self.client.get_market_data()
                if market_data:
                    current_price = market_data.get("last_price", 0)
                    if current_price > 0 and self.open_positions:
                        self.monitor_positions(current_price)
                
                logger.info(f"Balance: ${self.balance:.2f} | Trades today: {self.ai_brain.trades_today}")
            
            except KeyboardInterrupt:
                logger.info("Stopping bot...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                import traceback
                traceback.print_exc()
            
            time.sleep(config.POLLING_INTERVAL)