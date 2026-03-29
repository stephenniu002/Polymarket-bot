import os, asyncio, json, time, logging, requests
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from contextlib import asynccontextmanager
from utils import get_poly_price, send_telegram_msg, get_trading_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PolyBot")

# --- 🎯 实战配置 ---
TARGET_MARKET = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000 
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动行情流
    asyncio.create_task(stream.start())
    # 启动套利扫描器 (Worker)
    asyncio.create_task(run_worker_loop())
    yield

app = FastAPI(lifespan=lifespan)

class BinanceDataStream:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol, self.price = symbol, 0.0
        self.ws_url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','').lower()}@kline_1m"

    async def start(self):
        try:
            exchange = ccxt_async.binanceus()
            ticker = await exchange.fetch_ticker(self.symbol)
            self.price = float(ticker['last'])
            await exchange.close()
            logger.info(f"✅ 币安行情预热成功: {self.price}")
        except: pass
        
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("🟢 币安 WS 连接成功")
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceDataStream()

async def run_worker_loop():
    logger.info("⏳ Worker 准备就绪，等待 10 秒后进行鉴权...")
    await asyncio.sleep(10)
    
    # 鉴权测试
    client = get_trading_client()
    if client: logger.info("✅ [关键] Polymarket L2 鉴权成功！")
    else: logger.error("❌ [严重] 鉴权失败，请检查私钥和充值")

    while True:
        try:
            if stream.price > 0:
                bid, ask = get_poly_price(TARGET_MARKET["token_id"])
                if ask:
                    logger.info(f"📊 监控中 | B: {stream.price} | P: {ask}")
                    # 这里的逻辑可以根据需要开启实盘
                    if stream.price > TARGET_MARKET["trigger_p"] and ask < 0.60:
                        logger.warning("🎯 发现信号，发送模拟预警...")
                        send_telegram_msg(f"🧪 [测试] 触发买入信号: {ask}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            await asyncio.sleep(10)

@app.get("/")
async def health(): return {"status": "ok", "p": stream.price}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
