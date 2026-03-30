import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg

# --- 🎯 实战核心配置 ---
TRADES_LOG = "trades.json"
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, # 币安价格触发线
    "max_ask": 0.65,    # 最大允许买入价格
    "bet_amount": 2.0,  # 每单金额 (USDC)
    "dry_run": False    # 🚀 实战开启
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Gasless")

# --- 🛠️ 鉴权初始化 ---
def get_trading_client():
    try:
        pk = os.getenv("POLY_PRIVATE_KEY")
        api_key = os.getenv("POLY_API_KEY")
        api_secret = os.getenv("POLY_API_SECRET")
        passphrase = os.getenv("POLY_PASSPHRASE")
        
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
        client.set_api_creds(api_key, api_secret, passphrase)
        return client
    except Exception as e:
        logger.error(f"❌ 鉴权失败: {e}")
        return None

# --- 💸 自动交易引擎 ---
async def arb_worker():
    await asyncio.sleep(5)
    client = get_trading_client()
    if not client: return
    logger.info("🔥 实战引擎已就位，正在盯着 Polymarket...")
    
    while True:
        try:
            # 1. 监测币安价格
            if stream.price > TARGET_CONFIG["trigger_p"]:
                # 2. 获取 Poly 实盘价格
                bid, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask and ask < TARGET_CONFIG["max_ask"]:
                    logger.info(f"💸 满足条件，发起下单: {ask}")
                    resp = client.create_and_post_order(OrderArgs(
                        price=ask, size=TARGET_CONFIG["bet_amount"]/ask,
                        side="BUY", token_id=TARGET_CONFIG["token_id"]
                    ))
                    if resp.get("success"):
                        # 3. 记账
                        order_id = resp.get("orderID")
                        with open(TRADES_LOG, "a") as f:
                            f.write(json.dumps({"t": time.time(), "id": order_id, "p": ask, "profit": 0.02}) + "\n")
                        send_telegram_msg(f"✅ 实盘成交! ID: {order_id}")
                        await asyncio.sleep(300) # 冷却5分钟
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"运行异常: {e}")
            await asyncio.sleep(10)

# --- 📉 币安 WS ---
class BinanceStream:
    def __init__(self, symbol="btc/usdt"):
        self.price = 0.0
        self.url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','')}@kline_1m"
    async def start(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    logger.info("🟢 币安 WS 连接成功")
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceStream()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    asyncio.create_task(arb_worker())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root(): return {"status": "ok", "price": stream.price}

@app.post("/get_trades")
async def get_trades(request: Request):
    req = await request.json()
    if req.get("key") != CONTROL_KEY: return {"error": "403"}, 403
    if os.path.exists(TRADES_LOG): return FileResponse(TRADES_LOG)
    return {"msg": "no trades yet"}, 404
