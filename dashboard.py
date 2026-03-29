import os, asyncio, json, time, logging
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
        self.symbol, self.price, self.is_ready = symbol, 0.0, False
        self.ws_url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','').lower()}@kline_1m"

    async def start(self):
        try:
            exchange = ccxt_async.binanceus({'timeout': 5000})
            ticker = await exchange.fetch_ticker(self.symbol)
            self.price = float(ticker['last'])
            await exchange.close()
            self.is_ready = True
        except: pass
        await self._listen_ws()

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceDataStream()

@app.get("/")
async def health(): return {"status": "ok", "p": stream.price}

@app.get("/data")
async def get_data(): return [{"close": stream.price}]
