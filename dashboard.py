import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg, get_trading_client

# --- 🎯 核心配置 ---
TRADES_LOG = "trades.json"
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, 
    "max_ask": 0.65,    
    "bet_amount": 2.0,  
    "dry_run": True     # 🛡️ 看到鉴权成功后改为 False
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Live")

# --- 📝 自动记账函数 ---
def log_trade(data):
    try:
        trades = []
        if os.path.exists(TRADES_LOG):
            with open(TRADES_LOG, "r") as f: trades = json.load(f)
        trades.append(data)
        with open(TRADES_LOG, "w") as f: json.dump(trades[-50:], f)
    except Exception as e: logger.error(f"记账失败: {e}")

# --- 🚀 异步驱动引擎 ---
class BinanceStream:
    def __init__(self, symbol="btc/usdt"):
        self.price = 0.0
        self.url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','')}@kline_1m"
    async def start(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    logger.info("🟢 币安 WS 已连接")
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceStream()

async def arb_worker():
    client = await asyncio.to_thread(get_trading_client)
    if not client: return logger.error("❌ 鉴权失败")
    logger.info("🔥 Polymarket 监控中...")
    
    while True:
        try:
            if stream.price > 0:
                bid, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask and stream.price > TARGET_CONFIG["trigger_p"] and ask < TARGET_CONFIG["max_ask"]:
                    if TARGET_CONFIG["dry_run"]:
                        logger.warning(f"🧪 模拟触发: Ask {ask}")
                    else:
                        resp = await asyncio.to_thread(client.create_and_post_order, OrderArgs(
                            token_id=TARGET_CONFIG["token_id"], price=ask, 
                            size=TARGET_CONFIG["bet_amount"]/ask, side="BUY"
                        ))
                        if resp.get("success"):
                            log_trade({"t": time.strftime("%H:%M:%S"), "p": ask, "id": resp.get("orderID")})
                            send_telegram_msg(f"✅ 实盘成交！价格: {ask}")
                            await asyncio.sleep(300)
            await asyncio.sleep(5)
        except Exception as e: await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    asyncio.create_task(arb_worker())
    yield

app = FastAPI(lifespan=lifespan)

# --- 🚪 跨云取经接口 ---
@app.get("/")
async def root(): return {"status": "ok", "price": stream.price}

@app.post("/get_trades")
async def get_trades(request: Request):
    req = await request.json()
    if req.get("key") != CONTROL_KEY: return {"error": "Key Wrong"}, 403
    if os.path.exists(TRADES_LOG): return FileResponse(TRADES_LOG)
    return {"error": "No Trades Yet"}, 404
