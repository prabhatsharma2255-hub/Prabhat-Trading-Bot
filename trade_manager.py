import json
import os
from datetime import datetime
from typing import Optional, List, Dict

class TradeManager:
    def __init__(self, filepath="trades.json"):
        self.filepath = filepath
        self.data = {"open": [], "closed": []}
        self._load()
    
    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.data = json.load(f)
            except:
                self.data = {"open": [], "closed": []}
        else:
            self._save()
    
    def _save(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def open_trade(self, trade_id: str, symbol: str, side: str, entry_price: float,
                   tp: float, sl: float, size: float, open_time: str = None):
        if open_time is None:
            open_time = datetime.now().isoformat()
        
        trade = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "tp": tp,
            "sl": sl,
            "size": size,
            "open_time": open_time,
            "close_time": None,
            "close_price": None,
            "pnl": None,
            "status": "open",
            "close_reason": None
        }
        self.data["open"].append(trade)
        self._save()
        return trade
    
    def close_trade(self, trade_id: str, close_price: float, close_time: str = None, 
                   close_reason: str = "manual", pnl: float = None):
        if close_time is None:
            close_time = datetime.now().isoformat()
            
        for trade in self.data["open"]:
            if trade["id"] == trade_id:
                if pnl is None:
                    pnl = self._calculate_pnl(trade["side"], trade["entry_price"], close_price, trade["size"])
                
                trade["status"] = "closed"
                trade["close_price"] = close_price
                trade["close_time"] = close_time
                trade["close_reason"] = close_reason
                trade["pnl"] = pnl
                
                self.data["open"].remove(trade)
                self.data["closed"].append(trade)
                self._save()
                return trade
        return None
    
    def get_open_trades(self) -> List[Dict]:
        return self.data["open"]
    
    def get_closed_trades(self) -> List[Dict]:
        return self.data["closed"]
    
    def get_all_trades(self) -> List[Dict]:
        return self.data["open"] + self.data["closed"]
    
    def check_manual_close(self, exchange_positions: List[Dict], current_price: float) -> List[Dict]:
        updated = []
        for trade in list(self.data["open"]):
            still_open = False
            for pos in exchange_positions:
                pos_entry = float(pos.get("entry_price", 0))
                trade_entry = float(trade["entry_price"])
                if abs(pos_entry - trade_entry) < 10:
                    still_open = True
                    break
            
            if not still_open:
                close_price = current_price
                close_time = datetime.now().isoformat()
                pnl = self._calculate_pnl(trade["side"], trade["entry_price"], close_price, trade["size"])
                self.close_trade(trade["id"], close_price, close_time, "manual", pnl)
                updated.append(trade)
        return updated
    
    def _calculate_pnl(self, side: str, entry: float, exit_price: float, size: float):
        if side == "buy":
            return (exit_price - entry) * size
        else:
            return (entry - exit_price) * size
    
    def load_from_db(self, db_file="trades.db"):
        import sqlite3
        if not os.path.exists(db_file):
            return
        
        try:
            conn = sqlite3.connect(db_file)
            c = conn.cursor()
            c.execute("SELECT id, direction, entry_price, exit_price, pnl_usd, status, signals_fired, stop_loss, take_profit, size, leverage, timestamp_entry, timestamp_exit, outcome FROM trades")
            
            for row in c.fetchall():
                trade_id = str(row[0])
                direction = row[1]
                side = "buy" if direction == "LONG" else "sell"
                entry = float(row[2] or 0)
                exit_p = float(row[3] or 0) if row[3] else None
                pnl = float(row[4] or 0) if row[4] else None
                status = row[5]
                setup = row[6]
                sl = float(row[7] or 0)
                tp = float(row[8] or 0)
                size = float(row[9] or 0.001) * float(row[10] or 1)
                t_entry = row[11]
                t_exit = row[12]
                outcome = row[13]
                
                trade = {
                    "id": trade_id,
                    "symbol": "BTCUSD",
                    "side": side,
                    "entry_price": entry,
                    "tp": tp,
                    "sl": sl,
                    "size": size,
                    "open_time": t_entry,
                    "close_time": t_exit,
                    "close_price": exit_p,
                    "pnl": pnl,
                    "status": status,
                    "close_reason": outcome
                }
                
                if status == "open" and not any(t["id"] == trade_id for t in self.data["open"]):
                    self.data["open"].append(trade)
                elif status == "closed" and not any(t["id"] == trade_id for t in self.data["closed"]):
                    self.data["closed"].append(trade)
            
            conn.close()
            self._save()
        except Exception as e:
            print(f"Error loading from DB: {e}")