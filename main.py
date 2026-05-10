import asyncio
import time
from datetime import datetime
from loguru import logger
from config import config
from trader import PolymarketTrader
from utils import send_telegram_message, format_report
from binance_stream import BinanceStream
from strategy import DirectionalStrategy

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
strategy = DirectionalStrategy()

# Dictionary to hold Binance streams for each coin
binance_streams = {}

async def scan_market(coin: str):
    """Scan a single market for directional snipe opportunities."""
    try:
        stream = binance_streams.get(coin)
        if not stream or not stream.is_connected:
            return
            
        # Only trade in the T-15 to T-5 seconds window
        if not strategy.is_snipe_window():
            return
            
        delta = stream.get_delta_percentage()
        direction = strategy.analyze(delta)
        
        if direction == "NEUTRAL":
            return
            
        logger.info(f"[{coin}] Snipe Window Active! Delta: {delta:.3f}%. Predicted Direction: {direction}")
        
        success, profit = await trader.execute_directional_trade(coin, direction)
        
        if success:
            state.total_trades += 1
            state.trades_won += 1 # Mocking 100% win rate for executed trades in dry run
            state.balance += profit
            state.pnl_since_last_report += profit
            
            # To prevent multiple trades in the same window, we could add a cooldown here
            await asyncio.sleep(20)
            
    except Exception as e:
        logger.error(f"Error scanning market {coin}: {e}")

async def market_scanner_loop():
    """Main loop that concurrently scans all target markets."""
    logger.info(f"Starting market scanner loop for {len(config.TARGET_COINS)} markets...")
    
    while state.is_active:
        try:
            # Concurrently scan all markets using asyncio.gather
            tasks = [scan_market(coin) for coin in config.TARGET_COINS]
            await asyncio.gather(*tasks)
            
            # Wait 1 second before next scan (high frequency during snipe window)
            await asyncio.sleep(1) 
        except Exception as e:
            logger.error(f"Error in scanner loop: {e}")
            await asyncio.sleep(1)

async def reporter_loop():
    """Sends a Telegram report every 30 minutes."""
    while state.is_active:
        try:
            current_time = time.time()
            if current_time - state.last_report_time >= config.REPORT_INTERVAL: 
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
                    "active_markets": config.TARGET_COINS[:3] + ["..."],
                    "remark": "Directional Snipe Strategy Active."
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
    logger.info("🚀 Starting Polymarket Directional Snipe Bot...")
    if config.DRY_RUN:
        logger.info("🧪 Running in DRY RUN mode. No real trades will be executed.")
        
    # Initialize Binance streams
    for coin in config.TARGET_COINS:
        # Map hype to a proxy or skip if not on Binance
        symbol = f"{coin}usdt"
        if coin == "hype":
            symbol = "btcusdt" # Proxy for hype
            
        stream = BinanceStream(symbol)
        binance_streams[coin] = stream
        asyncio.create_task(stream.start())
        
    # Start concurrent tasks
    scanner_task = asyncio.create_task(market_scanner_loop())
    reporter_task = asyncio.create_task(reporter_loop())
    
    await asyncio.gather(scanner_task, reporter_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
