import os, asyncio, json, time, logging
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from contextlib import asynccontextmanager
from utils import get_poly_price, send_telegram_msg, get_trading_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Master")

# --- 🎯 目标配置 (建议先用现价附近的测试) ---
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000,
    "dry_run": True 
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚨 关键：先让 Web 启动，延迟启动耗时的 Worker
    logger.info("🚀 Web 服务就绪，10秒后启动后台扫描器...")
    asyncio.create_task(stream.start())
    asyncio.get_event_loop().call_later(10, lambda: asyncio.create_task(run_arb_worker()))
    yield

app = FastAPI(lifespan=lifespan)

class BinanceDataStream:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol, self.price = symbol, 0.0
        self.ws_url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','').lower()}@kline_1m"

    async def start(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("🟢 币安 WebSocket 已连接")
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: 
                await asyncio.sleep(5)

stream = BinanceDataStream()

async def run_arb_worker():
    # 🔑 这里的鉴权最耗时，必须异步执行
    logger.info("🔑 正在进行 Polymarket L2 鉴权...")
    client = await asyncio.to_thread(get_trading_client)
    
    if client:
        logger.info("🔥 [关键成功] Polymarket L2 鉴权通过！")
    else:
        logger.error("❌ [鉴权失败] 请检查环境变量和钱包余额")

    while True:
        try:
            if stream.price > 0:
                # 使用 to_thread 防止请求阻塞异步循环
                bid, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask:
                    logger.info(f"📊 实时比价 | B: {stream.price} | P: {ask}")
                    if stream.price > TARGET_CONFIG["trigger_p"] and ask < 0.60:
                        if TARGET_CONFIG["dry_run"]:
                            logger.warning(f"🧪 [模拟信号] 触发买入: {ask}")
                            send_telegram_msg(f"🧪 [模拟预警] 价格触发: {ask}")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            await asyncio.sleep(10)

@app.get("/")
async def health(): 
    # 极简响应，确保 Railway Health Check 永远返回 200
    return {"status": "ok", "p": stream.price}

if __name__ == "__main__":
    import uvicorn
    # 必须指定单 worker 模式
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), workers=1)
