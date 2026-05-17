import time
from datetime import datetime
from typing import Dict, Optional
import config
from delta_client import DeltaClient
from indicators import TechnicalIndicators
from ai_brain import ConfidenceEngine
from risk_manager import RiskManager
import dashboard


class TradingBot:
    def __init__(self, api_key: str, api_secret: str):
        self.client = DeltaClient(api_key, api_secret)
        self.ai_brain = ConfidenceEngine()
        self.risk_manager = RiskManager(config.CAPITAL)
        self.current_position = None
        self.last_analysis_time = 0

    def get_market_data(self, timeframe: str, limit: int = 100) -> list:
        candles = self.client.get_candles(config.SYMBOL, timeframe, limit)
        return candles if candles else []

    def analyze_market(self) -> Optional[Dict]:
        now = time.time()
        if now - self.last_analysis_time < config.POLLING_INTERVAL:
            return None

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing market...")

        candles = self.get_market_data("15m", 100)
        if not candles:
            print("No candles received")
            return None

        indicators = TechnicalIndicators(candles)
        data = indicators.all_indicators()

        price = data.get("current_price", 0)
        if price == 0:
            return None

        market = self.client.get_market_data()
        if market:
            data.update(market)

        result = self.ai_brain.analyze(data, price)
        self.last_analysis_time = now

        print(f"  Regime: {result['regime']}, Confidence: {result['confidence']:.1f}%, Signal: {result['signal']}")

        return result

    def execute_trade(self, analysis: Dict) -> bool:
        can_trade, reason = self.risk_manager.can_trade()
        if not can_trade:
            print(f"Cannot trade: {reason}")
            return False

        decision = analysis.get("decision", {})
        if not decision.get("should_trade", False):
            print("AI: No trade - low confidence")
            return False

        direction = decision.get("direction", "NONE")
        if direction == "NONE":
            return False

        price = decision.get("current_price", 0)
        stop_loss = decision.get("stop_loss", 0)
        take_profit = decision.get("take_profit", 0)
        risk_amount = decision.get("risk_amount", 0)
        leverage = decision.get("leverage", 1)

        if risk_amount <= 0:
            return False

        position_size = self.risk_manager.calculate_position_size(price, stop_loss, risk_amount)
        side = "buy" if direction == "LONG" else "sell"

        print(f">>> EXECUTING: {direction} {position_size:.4f} @ ${price:.2f} (leverage: {leverage}x)")

        order = self.client.place_order("market", side, position_size, None, stop_loss, take_profit, leverage)

        if order:
            self.current_position = {
                "side": side,
                "entry_price": price,
                "size": position_size,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_time": datetime.now().isoformat()
            }

            dashboard.log_trade(
                direction=direction,
                entry_price=price,
                exit_price=0,
                size=position_size,
                pnl=0,
                status="open",
                confidence=analysis.get("confidence", 0),
                regime=analysis.get("regime", "unknown")
            )
            return True
        return False

    def run(self):
        print("=" * 50)
        print("DELTA AI TRADING BOT STARTED")
        print(f"Capital: ${config.CAPITAL}, Max Risk: ${config.MAX_RISK_AMOUNT}")
        print(f"Mode: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")
        print("=" * 50)

        analysis = self.analyze_market()
        if analysis:
            self.execute_trade(analysis)

        print(f"\nNext analysis in {config.POLLING_INTERVAL} seconds...")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                time.sleep(config.POLLING_INTERVAL)
                analysis = self.analyze_market()
                if analysis:
                    self.execute_trade(analysis)
                stats = self.risk_manager.get_stats()
                print(f"Stats: {stats['total_trades']} trades, Win: {stats['win_rate']:.0f}%")

        except KeyboardInterrupt:
            print("\nBot stopped.")