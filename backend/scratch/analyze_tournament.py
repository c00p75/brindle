import sqlite3
from datetime import datetime

def analyze_performance(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get all tournament bots
    cur.execute("SELECT id, name FROM bots WHERE name LIKE 'Tournament:%'")
    bots = cur.fetchall()
    
    print(f"{'Bot Name':<30} | {'PnL ($)':>10} | {'PnL %':>8} | {'Trades':>6} | {'Last Active':<15}")
    print("-" * 80)
    
    for bot_id, bot_name in bots:
        # Get latest balance
        cur.execute(f"SELECT balance, at_ms FROM balance_snapshots WHERE bot_id = ? ORDER BY at_ms DESC LIMIT 1", (bot_id,))
        bal_data = cur.fetchone()
        
        # Get start balance
        cur.execute(f"SELECT balance, at_ms FROM balance_snapshots WHERE bot_id = ? ORDER BY at_ms ASC LIMIT 1", (bot_id,))
        start_data = cur.fetchone()
        
        # Get trade count
        cur.execute(f"SELECT COUNT(*) FROM fills WHERE bot_id = ?", (bot_id,))
        trade_count = cur.fetchone()[0]
        
        if bal_data and start_data:
            current_bal = bal_data[0]
            start_bal = start_data[0]
            pnl = current_bal - start_bal
            pnl_pct = (pnl / start_bal * 100) if start_bal != 0 else 0
            last_active = datetime.fromtimestamp(bal_data[1]/1000).strftime('%Y-%m-%d %H:%M')
            
            print(f"{bot_name:<30} | {pnl:>10.2f} | {pnl_pct:>7.2f}% | {trade_count:>6} | {last_active}")
        else:
            print(f"{bot_name:<30} | {'0.00':>10} | {'0.00%':>8} | {trade_count:>6} | {'No snapshots'}")
            
    conn.close()

if __name__ == "__main__":
    analyze_performance("/opt/brindle/backend/data/trading-bot.db")
