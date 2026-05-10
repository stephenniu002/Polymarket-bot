import asyncio
import time
from datetime import datetime
from loguru import logger
from config import config
from trader import PolymarketTrader
from utils import send_telegram_message, format_report

class BotState:
    def __init__(self):
        self.is_active = True
        self.start_time = time.time()
        self.last_report_time = time.time()
        self.balance = 1000.0 # Mock initial balance
        self.total_gas_cost = 0.0
        self.trades_won = 0
        self.total_trades = 0
        self.pnl_since_last_report = 0.0

state = BotState()
trader = PolymarketTrader()

async def scan_market(coin: str):
    """Scan a single market for arbitrage opportunities."""
    try:
        success, profit = await trader.execute_arbitrage(coin)
        
        if success:
            state.total_trades += 1
            state.trades_won += 1 # Mocking 100% win rate for executed trades in dry run
            state.balance += profit
            state.pnl_since_last_report += profit
            state.total_gas_cost += trader.gas_manager.get_gas_estimate_usd() * 2
            
    except Exception as e:
        logger.error(f"Error scanning market {coin}: {e}")

async def market_scanner_loop():
    """Main loop that concurrently scans all target markets."""
    logger.info(f"Starting market scanner loop for {len(config.TARGET_MARKETS)} markets...")
    
    while state.is_active:
        try:
            # Concurrently scan all markets using asyncio.gather
            tasks = [scan_market(market.split('-')[0]) for market in config.TARGET_MARKETS]
            await asyncio.gather(*tasks)
            
            # Wait 5 seconds before next scan
            await asyncio.sleep(5) 
        except Exception as e:
            logger.error(f"Error in scanner loop: {e}")
            await asyncio.sleep(5)

async def reporter_loop():
    """Sends a Telegram report every 30 minutes."""
    while state.is_active:
        try:
            current_time = time.time()
            # 1800 seconds = 30 minutes. Using 60 for testing.
            if current_time - state.last_report_time >= 60: 
                win_rate = (state.trades_won / state.total_trades * 100) if state.total_trades > 0 else 0
                
                report_data = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "balance": state.balance,
                    "pnl": state.pnl_since_last_report,
                    "gas_cost": state.total_gas_cost,
                    "win_rate": win_rate,
                    "wins": state.trades_won,
                    "total_trades": state.total_trades,
                    "status": "正常 (NORMAL)",
                    "active_markets": config.TARGET_MARKETS[:3] + ["..."],
                    "remark": "当前Gas费较低，策略运行效率高。" if state.total_gas_cost < 5 else "Gas费偏高，部分交易被过滤。"
                }
                
                report_msg = format_report(report_data)
                logger.info(f"Sending periodic report:\n{report_msg}")
                await send_telegram_message(report_msg)
                
                # Reset period stats
                state.pnl_since_last_report = 0.0
                state.last_report_time = current_time
                
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error in reporter loop: {e}")
            await asyncio.sleep(10)

async def main():
    logger.info("🚀 Starting Polymarket Arbitrage Bot...")
    if config.DRY_RUN:
        logger.info("🧪 Running in DRY RUN mode. No real trades will be executed.")
        
    # Start concurrent tasks
    scanner_task = asyncio.create_task(market_scanner_loop())
    reporter_task = asyncio.create_task(reporter_loop())
    
    await asyncio.gather(scanner_task, reporter_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
