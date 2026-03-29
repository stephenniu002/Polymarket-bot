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
    # 异步启动，不阻塞主进程
    asyncio.create_task(stream.start())
    yield
    logger.info("🛑 系统正在关闭...")

app = FastAPI(lifespan=lifespan)

class BinanceDataStream:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.price = 0.0
        self.is_ready = False
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_1m"

    async def start(self):
        try:
            exchange = ccxt_async.binanceus({'timeout': 5000})
            ticker = await exchange.fetch_ticker(self.symbol)
            self.price = float(ticker['last'])
            await exchange.close()
            self.is_ready = True
            logger.info(f"✅ 初始价格获取成功: {self.price}")
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
                        self.price = float(data['c'])
            except:
                await asyncio.sleep(5)

stream = BinanceDataStream()

@app.get("/")
async def health():
    # 极简响应，确保 Health Check 永不超时
    return {"status": "ok", "p": stream.price}

@app.get("/data")
async def get_data():
    # 抛弃重量级的 DataFrame，直接传数字，省内存
    return [{"timestamp": int(time.time()*1000), "close": stream.price}]

if __name__ == "__main__":
    import uvicorn
    # 强制单进程，减少内存压力
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), workers=1)
