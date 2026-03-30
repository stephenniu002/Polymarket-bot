import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg, get_trading_client

# --- 🎯 实战核心配置 (已开启实盘) ---
TRADES_LOG = "trades.json"
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, 
    "max_ask": 0.65,    
    "bet_amount": 2.0,  
    "dry_run": False     # 🚀 实弹射击模式已开启
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Live")

def log_trade(data):
    try:
        trades = []
        if os.path.exists(TRADES_LOG):
            with open(TRADES_LOG, "r") as f: trades = json.load(f)
        trades.append(data)
        with open(TRADES_LOG, "w") as f: json.dump(trades[-50:], f)
    except Exception as e: logger.error(f"记账失败: {e}")

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
    await asyncio.sleep(10)
    client = await asyncio.to_thread(get_trading_client)
    if not client: 
        logger.error("❌ 鉴权失败，请检查环境变量")
        return
    logger.info("🔥 实盘引擎启动，监控中...")
    
    while True:
        try:
            if stream.price > 0:
                bid, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask and stream.price > TARGET_CONFIG["trigger_p"] and ask < TARGET_CONFIG["max_ask"]:
                    logger.info(f"💸 触发下单: {ask}")
                    resp = await asyncio.to_thread(client.create_and_post_order, OrderArgs(
                        token_id=TARGET_CONFIG["token_id"], price=ask, 
                        size=TARGET_CONFIG["bet_amount"]/ask, side="BUY"
                    ))
                    if resp.get("success"):
                        order_id = resp.get("orderID")
                        log_trade({"time": time.strftime("%H:%M:%S"), "price": ask, "id": order_id, "profit": 0.01})
                        send_telegram_msg(f"✅ 实盘成交！ID: {order_id}")
                        await asyncio.sleep(300)
            await asyncio.sleep(5)
        except Exception as e: 
            logger.error(f"Worker 异常: {e}")
            await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    asyncio.create_task(arb_worker())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root(): return {"status": "ok", "msg": "龙虾哨兵在线", "price": stream.price}

@app.post("/get_trades")
async def get_trades(request: Request):
    req = await request.json()
    if req.get("key") != CONTROL_KEY: return {"error": "Key Wrong"}, 403
    if os.path.exists(TRADES_LOG): return FileResponse(TRADES_LOG)
    return {"error": "No Trades Yet"}, 404
