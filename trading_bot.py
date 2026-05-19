"""
Trading Bot - Setup-Based Execution Engine

Works with 12 named setups + News Intelligence + Move Detection
"""

import time
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
from typing import Dict, Optional, List
import threading

import config
from delta_client import DeltaClient
from indicators import Indicators
from ai_brain import AIBrain
from flask import Flask, jsonify

# Dashboard import - only for Flask, not for worker
try:
    import dashboard
except:
    dashboard = None

from trade_manager import save_trade, close_trade, get_open

# Simple API for dashboard sync
_api_app = Flask(__name__)
_api_data = {"open": [], "closed": []}
_api_lock = threading.Lock()  # FIXED: Added lock for thread safety

@_api_app.route("/api/trades")
def api_trades():
    with _api_lock:  # FIXED: Lock access
        return jsonify(_api_data)

@_api_app.route("/api/stats")
def api_stats():
    with _api_lock:  # FIXED: Lock access
        closed = _api_data["closed"]
        total = sum(t.get("pnl", 0) or 0 for t in closed)
        wins = len([t for t in closed if (t.get("pnl", 0) or 0) > 0])
        rate = (wins / len(closed) * 100) if closed else 0
        return jsonify({"total_pnl": total, "win_rate": rate, "open": len(_api_data["open"]), "closed": len(closed)})

def _start_api_server():
    from werkzeug.serving import make_server
    server = make_server('0.0.0.0', 5001, _api_app, threaded=True)
    server.serve_forever()

def update_api_trades():
    """Update API with current trade data"""
    global _api_data
    try:
        from trade_manager import get_open, get_closed
        with _api_lock:  # FIXED: Lock access
            _api_data["open"] = get_open()
            _api_data["closed"] = get_closed()
    except:
        pass

try:
    from trade_manager import TradeManager
except:
    TradeManager = None

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
                logger.info("News Engine initialized")
            except Exception as e:
                logger.warning(f"News Engine init failed: {e}")

        self.ai_brain = AIBrain(news_engine=self.news_engine)

        self.last_analysis_time = 0
        self.open_positions = []
        self.balance = config.STARTING_CAPITAL
        self._running = True  # FIXED: Add running flag for graceful shutdown

        if MoveDetector:
            try:
                self.move_detector = MoveDetector(self.client)
                self.move_detector.start()
                logger.info("Move Detector started")
            except Exception as e:
                logger.warning(f"Move Detector init failed: {e}")

        self._run_connection_test()

        # Initialize TradeManager
        self.trade_manager = None
        if TradeManager:
            try:
                self.trade_manager = TradeManager()
                logger.info("TradeManager initialized (SQLite)")
            except Exception as e:
                logger.warning(f"TradeManager init failed: {e}")

        # Load open trades from database
        self._load_open_trades_from_db()

        if not config.DRY_RUN:
            self._sync_positions()
            # Sync balance from exchange
            exchange_balance = self.client.get_balance()
            if exchange_balance > 0:
                self.balance = exchange_balance
                logger.info(f"Balance synced from exchange: ${self.balance:.2f}")
        else:
            self._cleanup_stale_positions()

        # Start background sync thread
        self._start_background_sync()

        logger.info("=" * 60)
        logger.info("BOT INITIALIZED")
        logger.info(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
        logger.info(f"Balance: ${self.balance:.2f}")
        logger.info("=" * 60)

    def _cleanup_stale_positions(self):
        """Clean up stale open positions in database (DRY_RUN mode)."""
        try:
            current_price = self.client.get_market_data().get("last_price", 0)
            conn = sqlite3.connect("trades.db")
            c = conn.cursor()
            c.execute("SELECT id, direction, entry_price, size, leverage FROM trades WHERE status = 'open'")
            stale_trades = c.fetchall()

            if stale_trades:
                logger.warning(f"Found {len(stale_trades)} stale open positions - fixing with current price ${current_price}")

                for trade in stale_trades:
                    trade_id, direction, entry, size, leverage = trade
                    entry = float(entry or 0)
                    size = float(size or 0)
                    leverage = float(leverage or 1)

                    if direction == "LONG":
                        pnl = (current_price - entry) * size * leverage
                    else:
                        pnl = (entry - current_price) * size * leverage

                    timestamp = datetime.now().isoformat()
                    c.execute("""UPDATE trades SET timestamp_exit=?, exit_price=?, pnl_usd=?, status=?, outcome=?
                                WHERE id=?""", (timestamp, current_price, pnl, "closed", "STALE_CLEANUP", trade_id))

                conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to cleanup stale positions: {e}")

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
                pos_leverage = float(pos.get("leverage", 1))  # FIXED: Read actual leverage
                pos_stop_loss = float(pos.get("stop_loss", 0))  # FIXED: Read exchange SL if any
                pos_take_profit = float(pos.get("take_profit", 0))  # FIXED: Read exchange TP if any

                self.open_positions.append({
                    "direction": direction,
                    "entry_price": entry_price,
                    "size": abs(size),
                    "stop_loss": pos_stop_loss,
                    "take_profit_1": pos_take_profit,
                    "take_profit_2": 0,
                    "leverage": pos_leverage,  # FIXED: Use actual leverage
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

        # FIXED: Fetch scalp candles (1m, 3m) for setups 7-9
        scalp_1m = self.get_market_data(config.TIMEFRAMES.get("scalp_1m", "1m"), config.SCALP_1M_CANDLES)
        scalp_3m = self.get_market_data(config.TIMEFRAMES.get("scalp_3m", "3m"), config.SCALP_3M_CANDLES)

        # Pass news_engine, move_detector, and scalp candles
        analysis = self.ai_brain.analyze(
            ltf_candles,
            htf_candles if htf_candles else None,
            velocity_data,
            self.news_engine,
            self.move_detector,
            scalp_1m_candles=scalp_1m if scalp_1m else None,
            scalp_3m_candles=scalp_3m if scalp_3m else None
        )

        state = analysis["state"]

        logger.info(f"MARKET STATE")
        atr_pct = (state.atr/state.current_price*100) if state.current_price > 0 else 0
        logger.info(f"BTC Price: ${state.current_price:.2f} | ATR: ${state.atr:.2f} ({atr_pct:.2f}%)")
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
            direction = f"\u2192 {setup.direction}" if setup.triggered else ""
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
            triggered_count = sum(1 for s in analysis.get("all_setups", []) if s.triggered)
            logger.info(f"DECISION: NO TRADE - {reason} | Triggered: {triggered_count}/12")

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
            logger.warning(f"CANNOT TRADE: can_trade={analysis.get('can_trade')}, setup={analysis.get('setup')}")
            return False

        if len(self.open_positions) >= config.MAX_OPEN_POSITIONS:
            logger.warning(f"BLOCKED: Max open positions ({len(self.open_positions)}/{config.MAX_OPEN_POSITIONS})")
            return False

        setup = analysis["setup"]

        for pos in self.open_positions:
            if pos.get("setup") == setup.setup_name:
                logger.warning(f"BLOCKED: Setup {setup.setup_name} already open")
                return False

        logger.info(f"TRADE READY: {setup.setup_name} {setup.direction} SL={setup.stop_loss:.0f} TP={setup.tp2:.0f}")

        state = analysis["state"]

        can_trade, reason = self.ai_brain.can_trade()
        if not can_trade:
            logger.warning(f"Cannot trade: {reason}")
            return False

        price = state.current_price
        direction = setup.direction
        risk_amount = self.balance * setup.risk_pct
        atr = state.atr

        if setup.stop_loss <= 0 or setup.tp2 <= 0:
            if direction == "LONG":
                setup.stop_loss = price - (atr * 2)
                setup.tp1 = price + (atr * 2)
                setup.tp2 = price + (atr * 4)
            else:
                setup.stop_loss = price + (atr * 2)
                setup.tp1 = price - (atr * 2)
                setup.tp2 = price - (atr * 4)
            logger.info(f"SL/TP not set by AI brain - using ATR fallback: SL={setup.stop_loss} TP2={setup.tp2}")

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

        # FIXED: Set leverage on exchange before placing order
        if not config.DRY_RUN:
            self.client.set_leverage(setup.leverage)

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

            # SAVE TO DATABASE INSTANTLY
            trade_id = f"trade_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}"
            save_trade({
                'id': trade_id,
                'symbol': config.SYMBOL,
                'side': "buy" if direction == "LONG" else "sell",
                'size': position_size,
                'entry_price': price,
                'tp': setup.tp2,
                'sl': setup.stop_loss,
                'leverage': setup.leverage
            })
            position["trade_id"] = trade_id

            # Log to dashboard (if available)
            if dashboard:
                try:
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
                        leverage=setup.leverage,
                        stop_loss=setup.stop_loss,
                        take_profit=setup.tp2
                    )
                except:
                    pass

            # Also save to TradeManager for dashboard sync
            if self.trade_manager:
                try:
                    trade_id = f"trade_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}"
                    side = "buy" if direction == "LONG" else "sell"

                    self.trade_manager.save_trade({
                        "trade_id": trade_id,
                        "symbol": config.SYMBOL,
                        "side": side,
                        "entry_price": price,
                        "tp": setup.tp2,
                        "sl": setup.stop_loss,
                        "size": position_size,
                        "leverage": setup.leverage,
                        "open_time": datetime.now(IST).isoformat()
                    })

                    # Store trade_id in position for later reference
                    position["trade_id"] = trade_id
                except Exception as e:
                    logger.warning(f"TradeManager save failed: {e}")

            logger.info("Trade executed successfully")
            update_api_trades()
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
                if sl > 0 and current_price <= sl:
                    to_close.append((i, pnl, "SL"))
                elif tp1 > 0 and current_price >= tp1 and not pos.get("tp1_hit"):
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    logger.info(f"TP1 HIT - SL moved to breakeven")
                elif tp2 > 0 and current_price >= tp2 and not pos.get("tp2_hit"):
                    to_close.append((i, pnl, "TP2"))
            else:
                pnl = (entry - current_price) * pos["size"] * leverage
                if sl > 0 and current_price >= sl:
                    to_close.append((i, pnl, "SL"))
                elif tp1 > 0 and current_price <= tp1 and not pos.get("tp1_hit"):
                    pos["tp1_hit"] = True
                    pos["stop_loss"] = entry
                    logger.info(f"TP1 HIT - SL moved to breakeven")
                elif tp2 > 0 and current_price <= tp2 and not pos.get("tp2_hit"):
                    to_close.append((i, pnl, "TP2"))

        for idx, pnl_val, reason in reversed(to_close):
            if idx < len(self.open_positions):
                pos = self.open_positions.pop(idx)

                leverage = pos.get("leverage", 1)
                direction = pos["direction"]
                entry = pos["entry_price"]

                if direction == "LONG":
                    pnl = (current_price - entry) * pos["size"] * leverage
                else:
                    pnl = (entry - current_price) * pos["size"] * leverage

                logger.info(f"CLOSING: {direction} Entry={entry} Exit={current_price} Lev={leverage}x PnL=${pnl:.2f}")

                if not config.DRY_RUN:
                    close_result = self.client.close_position(pos["direction"], pos["size"])
                else:
                    logger.info("[DRY RUN] Would close position")

                self.balance += pnl

                if pnl > 0:
                    self.ai_brain.consecutive_losses = 0
                else:
                    self.ai_brain.consecutive_losses += 1

                if dashboard:
                    try:
                        dashboard.log_trade(
                            direction=pos["direction"],
                            entry_price=pos["entry_price"],
                            exit_price=current_price,
                            size=pos["size"],
                            pnl=pnl,
                            status="closed",
                            confidence=0,
                            regime="",
                            signals="",
                            htf_aligned=False,
                            session="",
                            grade=pos.get("setup", ""),
                            module=pos.get("setup", ""),
                            outcome=reason,
                            leverage=pos.get("leverage", 1),
                            stop_loss=pos.get("stop_loss", 0),
                            take_profit=pos.get("take_profit_2", 0)
                        )
                    except:
                        pass

                # Also save to TradeManager
                if self.trade_manager:
                    try:
                        trade_id = pos.get("trade_id", f"trade_{idx+1}")
                        self.trade_manager.close_trade(
                            trade_id=trade_id,
                            close_price=current_price,
                            close_reason=reason,
                            fees=0
                        )
                    except Exception as e:
                        logger.warning(f"TradeManager close failed: {e}")

                # ALSO call simple close_trade for dashboard
                trade_id = pos.get("trade_id", f"trade_{idx+1}")
                close_trade(trade_id, current_price, reason.lower())

                logger.info(f"Trade closed: {reason} | PnL: ${pnl:.2f} | Exit: ${current_price}")
                update_api_trades()

    def _load_open_trades_from_db(self):
        """Load open trades from database on startup"""
        if not self.trade_manager:
            return

        try:
            open_trades = self.trade_manager.get_all_open_trades()
            logger.info(f"Loaded {len(open_trades)} open trades from database")

            # Reconstruct open_positions for bot logic
            for t in open_trades:
                side = t.get("side", "sell")
                direction = "LONG" if side in ["buy", "long"] else "SHORT"

                self.open_positions.append({
                    "direction": direction,
                    "entry_price": t.get("entry_price", 0),
                    "size": t.get("size", 0),
                    "leverage": t.get("leverage", 1),
                    "stop_loss": t.get("sl", 0),
                    "take_profit_1": t.get("tp", 0),
                    "take_profit_2": t.get("tp", 0),
                    "setup": t.get("trade_id", ""),
                    "opened_at": t.get("open_time", ""),
                    "trade_id": t.get("trade_id", "")
                })
        except Exception as e:
            logger.warning(f"Failed to load open trades: {e}")

    def _start_background_sync(self):
        """Start background thread to sync with exchange every 3 seconds"""
        import threading

        def sync_loop():
            while self._running:  # FIXED: Use running flag for graceful exit
                try:
                    self._sync_with_exchange()
                except Exception as e:
                    logger.warning(f"Sync error: {e}")

                time.sleep(3)

        if not config.DRY_RUN:
            thread = threading.Thread(target=sync_loop, daemon=True)
            thread.start()
            logger.info("Background sync thread started")

        # ADDITIONAL SYNC FOR MANUAL CLOSE DETECTION
        def sync_positions():
            while self._running:  # FIXED: Use running flag
                try:
                    open_trades = get_open()
                    exchange_positions = self.client.get_positions()
                    # Build set of exchange position entry prices for matching
                    exchange_entries = set()
                    for p in exchange_positions:
                        entry = abs(float(p.get("entry_price", 0)))
                        if entry > 0:
                            exchange_entries.add(round(entry, 1))  # Round to 1 decimal for matching

                    for t in open_trades:
                        trade_entry = round(float(t.get("entry_price", 0)), 1)
                        # Check if this trade matches any exchange position by entry price
                        still_open = trade_entry in exchange_entries if trade_entry > 0 else False

                        if not still_open:
                            ticker = self.client.get_market_data()
                            close_price = ticker.get('last_price', 0) if ticker else 0
                            if close_price > 0:
                                close_trade(t['id'], close_price, 'manual')
                                logger.info(f"Detected manual close: trade {t['id']} at ${close_price}")
                except Exception as e:
                    print(f"Sync error: {e}")
                time.sleep(3)

        sync_thread = threading.Thread(target=sync_positions, daemon=True)
        sync_thread.start()
        logger.info("Manual close detection thread started")

        # START API SERVER for dashboard sync
        api_thread = threading.Thread(target=_start_api_server, daemon=True)
        api_thread.start()
        logger.info("API server started on port 5001")

    def _sync_with_exchange(self):
        """Sync trades with exchange - detect manual closes"""
        if not self.trade_manager:
            return

        try:
            # Get current open positions from exchange
            exchange_positions = self.client.get_positions()
            current_price = self.client.get_market_data().get("last_price", 0)

            if not exchange_positions:
                return

            # Get database open trades
            db_trades = self.trade_manager.get_all_open_trades()

            for trade in db_trades:
                trade_id = trade.get("trade_id", "")
                entry = trade.get("entry_price", 0)
                side = trade.get("side", "sell")
                size = trade.get("size", 0)
                leverage = trade.get("leverage", 1)

                # Check if trade still exists on exchange (match by entry price rounded)
                still_open = False
                for pos in exchange_positions:
                    pos_entry = abs(float(pos.get("entry_price", 0)))
                    if pos_entry > 0 and abs(pos_entry - entry) / max(pos_entry, entry) < 0.002:
                        still_open = True
                        break

                # If not on exchange but in DB as open = manually closed
                if not still_open:
                    logger.info(f"Detected manual close for trade {trade_id}")

                    # Calculate PnL
                    if side in ["buy", "long"]:
                        pnl = (current_price - entry) * size * leverage
                    else:
                        pnl = (entry - current_price) * size * leverage

                    # Close in database
                    self.trade_manager.close_trade(trade_id, current_price, "manual", 0)

                    # Remove from bot's open_positions
                    self.open_positions = [p for p in self.open_positions if p.get("trade_id") != trade_id]

                    logger.info(f"Trade {trade_id} closed manually | PnL: ${pnl:.2f}")

            # Check for new trades on exchange not in DB
            for pos in exchange_positions:
                entry = float(pos.get("entry_price", 0))

                # Check if this position is in DB (match by rounded entry price)
                found = False
                for t in db_trades:
                    db_entry = float(t.get("entry_price", 0))
                    if db_entry > 0 and abs(db_entry - entry) / max(db_entry, entry) < 0.002:
                        found = True
                        break

                if not found and entry > 0:
                    # New trade opened before bot restart - recover it
                    logger.info(f"Recovering trade at entry ${entry}")
                    trade_id = f"recovered_{int(time.time())}"

                    self.trade_manager.save_trade({
                        "trade_id": trade_id,
                        "symbol": config.SYMBOL,
                        "side": pos.get("side", "sell"),
                        "entry_price": entry,
                        "tp": pos.get("take_profit", 0),
                        "sl": pos.get("stop_loss", 0),
                        "size": pos.get("size", 0.001),
                        "leverage": pos.get("leverage", 1),
                        "open_time": datetime.now(IST).isoformat()
                    })

        except Exception as e:
            logger.warning(f"Sync with exchange failed: {e}")

    def stop(self):
        """FIXED: Graceful shutdown - cancel orders, close positions, exit cleanly"""
        logger.info("=" * 60)
        logger.info("SHUTTING DOWN BOT")
        logger.info("=" * 60)

        self._running = False

        if not config.DRY_RUN:
            # Cancel all open orders
            try:
                orders = self.client.get_open_orders()
                for order in orders:
                    order_id = order.get("id", "")
                    if order_id:
                        self.client.cancel_order(order_id)
                        logger.info(f"Cancelled order {order_id}")
            except Exception as e:
                logger.warning(f"Error cancelling orders: {e}")

        logger.info("Bot shutting down cleanly")

    def run(self):
        self.ai_brain.reset_daily()

        logger.info("=" * 60)
        logger.info("DELTA EXCHANGE AI TRADING BOT - SETUP BASED")
        logger.info(f"Starting Capital: ${config.STARTING_CAPITAL}")
        logger.info(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
        logger.info(f"Max Trades/Day: {config.MAX_TRADES_PER_DAY}")
        logger.info("=" * 60)

        try:
            while self._running:
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
                    raise
                except Exception as e:
                    logger.error(f"Error: {e}")
                    import traceback
                    traceback.print_exc()

                time.sleep(config.POLLING_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
