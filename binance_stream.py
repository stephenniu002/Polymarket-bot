import asyncio
import json
import websockets
from loguru import logger

class BinanceStream:
    def __init__(self, symbol="btcusdt"):
        self.symbol = symbol.lower()
        self.url = f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_1m"
        self.current_price = 0.0
        self.window_open_price = 0.0
        self.is_connected = False

    async def start(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    self.is_connected = True
                    logger.info(f"🟢 Binance WS Connected for {self.symbol.upper()}")
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        kline = data['k']
                        
                        self.current_price = float(kline['c'])
                        
                        # If this is the first minute of a 5-minute window (e.g., 00, 05, 10)
                        # we record the open price
                        minute = int(kline['t'] / 60000) % 60
                        if minute % 5 == 0 and not kline['x']: # Not closed yet
                            if self.window_open_price == 0.0:
                                self.window_open_price = float(kline['o'])
                                logger.debug(f"Window Open Price Set: {self.window_open_price}")
                        
                        # Reset open price when window closes
                        if minute % 5 == 4 and kline['x']:
                            self.window_open_price = 0.0
                            
            except Exception as e:
                self.is_connected = False
                logger.warning(f"⚠️ Binance WS Disconnected: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def get_delta_percentage(self):
        """Returns the percentage change from window open price"""
        if self.window_open_price == 0.0 or self.current_price == 0.0:
            return 0.0
        return (self.current_price - self.window_open_price) / self.window_open_price * 100
