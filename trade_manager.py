"""
TradeManager - SQLite-based trade database
Saves permanently, never loses data on crash/restart
"""

import sqlite3
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import json

DB_FILE = "trades.db"

class TradeManager:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        # Don't recreate - just add missing columns to existing
        self._add_missing_columns()
        self.migrate_from_json()
        self.migrate_from_old_db()
    
    def _add_missing_columns(self):
        """Add missing columns to existing database"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Add trade_id if missing
            try:
                c.execute("ALTER TABLE trades ADD COLUMN trade_id TEXT UNIQUE")
            except:
                pass
            
            # Add other columns
            for col, dtype in [
                ("side", "TEXT"),
                ("margin_used", "REAL"),
                ("pnl_percent", "REAL"),
                ("close_reason", "TEXT"),
                ("exchange", "TEXT DEFAULT 'delta'"),
                ("fees", "REAL DEFAULT 0"),
                ("net_pnl", "REAL")
            ]:
                try:
                    c.execute(f"ALTER TABLE trades ADD COLUMN {col} {dtype}")
                except:
                    pass
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Column add error: {e}")
    
    def migrate_from_json(self):
        """Import trades from trades.json if exists"""
        if not os.path.exists("trades.json"):
            return
        
        try:
            with open("trades.json", "r") as f:
                data = json.load(f)
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Import open trades
            for trade in data.get("open", []):
                if not self._trade_id_exists(trade.get("id", "")):
                    self._insert_from_json(c, trade)
            
            # Import closed trades
            for trade in data.get("closed", []):
                if not self._trade_id_exists(trade.get("id", "")):
                    self._insert_from_json(c, trade)
            
            conn.commit()
            conn.close()
            
            # Backup old JSON
            os.rename("trades.json", "trades_backup.json")
            print("Migrated trades from JSON to SQLite")
        except Exception as e:
            print(f"Migration error: {e}")
    
    def migrate_from_old_db(self, old_db: str = "trades.db"):
        """Import trades from old SQLite database if exists"""
        if not os.path.exists(old_db):
            return
        
        try:
            old_conn = sqlite3.connect(old_db)
            old_c = old_conn.cursor()
            
            # Get all trades from old DB - check columns first
            old_c.execute("PRAGMA table_info(trades)")
            cols = [row[1] for row in old_c.fetchall()]
            print(f"Old DB columns: {cols}")
            
            # Build dynamic query based on available columns
            needed_cols = ['id', 'direction', 'entry_price', 'exit_price', 'pnl_usd', 'status', 
                          'signals_fired', 'stop_loss', 'take_profit', 'size', 'leverage', 
                          'timestamp_entry', 'timestamp_exit', 'outcome']
            
            select_cols = [c for c in needed_cols if c in cols]
            old_c.execute(f"SELECT {','.join(select_cols)} FROM trades")
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            for row in old_c.fetchall():
                trade_id = str(row[0])
                if self._trade_id_exists(trade_id):
                    continue
                
                # Map available columns
                data = dict(zip(select_cols, row))
                
                direction = data.get('direction', 'SHORT')
                side = "buy" if direction == "LONG" else "sell"
                entry = float(data.get('entry_price', 0) or 0)
                exit_p = data.get('exit_price')
                pnl = float(data.get('pnl_usd', 0) or 0) if data.get('pnl_usd') else None
                status = data.get('status', 'closed')
                sl = float(data.get('stop_loss', 0) or 0)
                tp = float(data.get('take_profit', 0) or 0)
                size = float(data.get('size', 0.001) or 0.001)
                lev = int(data.get('leverage', 1) or 1)
                open_time = data.get('timestamp_entry')
                close_time = data.get('timestamp_exit')
                close_reason = data.get('outcome')
                
                margin = size * entry / lev if lev > 0 else size * entry
                
                c.execute('''INSERT OR IGNORE INTO trades (
                    trade_id, symbol, side, entry_price, close_price, tp, sl,
                    size, leverage, margin_used, pnl, status, close_reason, 
                    open_time, close_time, fees, net_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (trade_id, "BTCUSD", side, entry, exit_p, tp, sl,
                     size, lev, margin, pnl, status, close_reason,
                     open_time, close_time, 0, pnl))
            
            conn.commit()
            conn.close()
            old_conn.close()
            print("Migrated trades from old SQLite database")
        except Exception as e:
            print(f"Old DB migration error: {e}")
    
    def _trade_id_exists(self, trade_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE trade_id = ?", (trade_id,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    
    def _insert_from_json(self, c, trade: Dict):
        try:
            c.execute('''INSERT INTO trades (
                trade_id, symbol, side, entry_price, close_price, tp, sl,
                size, leverage, pnl, status, close_reason, open_time, close_time, fees
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    trade.get("id", ""),
                    trade.get("symbol", "BTCUSD"),
                    trade.get("side", "sell"),
                    trade.get("entry_price", 0),
                    trade.get("close_price"),
                    trade.get("tp", 0),
                    trade.get("sl", 0),
                    trade.get("size", 0),
                    1,
                    trade.get("pnl"),
                    trade.get("status", "closed"),
                    trade.get("close_reason"),
                    trade.get("open_time"),
                    trade.get("close_time"),
                    0
                )
            )
        except:
            pass
    
    def save_trade(self, trade: Dict) -> bool:
        """Save a new trade to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Calculate margin
            margin = trade.get("size", 0) * trade.get("entry_price", 0) / max(trade.get("leverage", 1), 1)
            
            c.execute('''INSERT INTO trades (
                trade_id, symbol, side, entry_price, tp, sl,
                size, leverage, margin_used, status, open_time, exchange
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    trade.get("trade_id"),
                    trade.get("symbol", "BTCUSD"),
                    trade.get("side", "sell"),
                    trade.get("entry_price", 0),
                    trade.get("tp", 0),
                    trade.get("sl", 0),
                    trade.get("size", 0),
                    trade.get("leverage", 1),
                    margin,
                    "open",
                    trade.get("open_time", datetime.now(timezone.utc).isoformat()),
                    trade.get("exchange", "delta")
                )
            )
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Save trade error: {e}")
            return False
    
    def update_trade(self, trade_id: str, updates: Dict) -> bool:
        """Update an existing trade"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [trade_id]
            
            c.execute(f"UPDATE trades SET {set_clause} WHERE trade_id = ?", values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Update trade error: {e}")
            return False
    
    def get_all_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY open_time DESC")
        rows = c.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_all_closed_trades(self, limit: int = 100) -> List[Dict]:
        """Get all closed trades, newest first"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM trades WHERE status = 'closed' ORDER BY close_time DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_all_trades(self) -> List[Dict]:
        """Get all trades"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM trades ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Check which column exists for PnL
        c.execute("PRAGMA table_info(trades)")
        cols = [row[1] for row in c.fetchall()]
        pnl_col = "pnl" if "pnl" in cols else "pnl_usd"
        fees_col = "fees" if "fees" in cols else "0"
        
        # Closed trades stats
        try:
            c.execute(f"SELECT COUNT(*), SUM({pnl_col}), SUM({fees_col}) FROM trades WHERE status = 'closed'")
            result = c.fetchone()
            total_count = result[0] or 0
            total_pnl = result[1] or 0
            total_fees = result[2] or 0
        except:
            total_count, total_pnl, total_fees = 0, 0, 0
        
        # Wins
        try:
            c.execute(f"SELECT COUNT(*) FROM trades WHERE status = 'closed' AND {pnl_col} > 0")
            wins = c.fetchone()[0] or 0
        except:
            wins = 0
        
        # Best/worst trade
        try:
            c.execute(f"SELECT MAX({pnl_col}), MIN({pnl_col}) FROM trades WHERE status = 'closed'")
            result = c.fetchone()
            best = result[0] or 0
            worst = result[1] or 0
        except:
            best, worst = 0, 0
        
        # Win rate
        win_rate = (wins / total_count * 100) if total_count > 0 else 0
        
        # Average trade
        avg_trade = total_pnl / total_count if total_count > 0 else 0
        
        # Open positions
        try:
            c.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
            open_count = c.fetchone()[0] or 0
        except:
            open_count = 0
        
        conn.close()
        
        return {
            "total_trades": total_count,
            "total_pnl": round(total_pnl, 2),
            "net_pnl": round(total_pnl - total_fees, 2),
            "total_fees": round(total_fees, 2),
            "wins": wins,
            "win_rate": round(win_rate, 2),
            "best_trade": round(best, 2),
            "worst_trade": round(worst, 2),
            "avg_trade": round(avg_trade, 2),
            "open_positions": open_count
        }
    
    def trade_exists(self, trade_id: str) -> bool:
        """Check if trade exists"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE trade_id = ?", (trade_id,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    
    def close_trade(self, trade_id: str, close_price: float, close_reason: str, 
                   fees: float = 0) -> bool:
        """Close a trade with PnL calculation"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get trade details
            c.execute("SELECT entry_price, size, leverage, side FROM trades WHERE trade_id = ?", (trade_id,))
            row = c.fetchone()
            
            if not row:
                conn.close()
                return False
            
            entry, size, leverage, side = row
            
            # Calculate PnL
            if side in ["buy", "long"]:
                pnl = (close_price - entry) * size * leverage
            else:  # sell/short
                pnl = (entry - close_price) * size * leverage
            
            pnl_percent = (pnl / (entry * size * leverage)) * 100 if (entry * size * leverage) > 0 else 0
            net_pnl = pnl - fees
            
            close_time = datetime.now(timezone.utc).isoformat()
            
            c.execute('''UPDATE trades SET 
                close_price = ?, pnl = ?, pnl_percent = ?, 
                fees = ?, net_pnl = ?, status = ?, 
                close_reason = ?, close_time = ?
                WHERE trade_id = ?''',
                (close_price, round(pnl, 2), round(pnl_percent, 2),
                 fees, round(net_pnl, 2), "closed", 
                 close_reason, close_time, trade_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Close trade error: {e}")
            return False
    
    def get_trade_by_id(self, trade_id: str) -> Optional[Dict]:
        """Get a specific trade by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
        row = c.fetchone()
        conn.close()
        
        return dict(row) if row else None


# Alias methods for compatibility (without causing recursion)
    def get_open_trades(self):
        return self.get_all_open_trades()
    
    def get_closed_trades(self):
        return self.get_all_closed_trades()


# Standalone functions for easy import
def get_trade_manager() -> TradeManager:
    return TradeManager()