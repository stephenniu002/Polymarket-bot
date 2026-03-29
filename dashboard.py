import os, asyncio, json, time, logging
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataHub")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    yield

app = FastAPI(lifespan=lifespan)

class BinanceDataStream:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.df = pd.DataFrame(columns=['timestamp', 'close'])
        self.is_ready = False
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_1m"

    async def start(self):
        try:
            exchange = ccxt_async.binanceus({'timeout': 10000})
            ohlcv = await exchange.fetch_ohlcv(self.symbol, '1m', limit=10)
            self.df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            await exchange.close()
            self.is_ready = True
            logger.info("✅ Binance.us 历史数据就绪")
        except Exception as e:
            logger.error(f"⚠️ 预热失败: {e}")
        await self._listen_ws()

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("🟢 Binance.us WS 已连接")
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)['k']
                        new_price = float(data['c'])
                        if not self.df.empty:
                            self.df.iloc[-1, 1] = new_price # 仅更新最新价
                        else:
                            self.df = pd.DataFrame([[time.time()*1000, new_price]], columns=['timestamp', 'close'])
            except:
                await asyncio.sleep(5)

stream = BinanceDataStream()

@app.get("/")
async def health():
    return {"status": "ok", "ready": stream.is_ready}

@app.get("/data")
async def get_data():
    if stream.df.empty: return []
    return stream.df.tail(5).to_dict(orient='records')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
