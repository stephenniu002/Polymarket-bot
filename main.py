import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg

# --- 🛡️ 1. 风控层 (RiskManager) ---
class RiskManager:
    def __init__(self):
        self.daily_loss = 0.0
        self.loss_streak = 0
        self.is_locked = False
        self.max_daily_loss = -20.0  # 强制止损：每天最多亏20u
        self.max_streak = 5           # 连亏保护：连错5单必停
        self.last_reset = time.strftime("%Y-%m-%d")

    def check(self, balance):
        # 每日重置限额
        today = time.strftime("%Y-%m-%d")
        if today != self.last_reset:
            self.daily_loss = 0.0
            self.last_reset = today

        if self.is_locked: return False, "🔴 紧急停火中"
        if self.daily_loss <= self.max_daily_loss: return False, "🛑 触及日损限额"
        if self.loss_streak >= self.max_streak: return False, "📉 连亏保护触发"
        if balance < 10.0: return False, "💸 余额警戒(低于10u)"
        return True, "🟢 准许作战"

    def update(self, profit):
        self.daily_loss += profit
        if profit < 0: self.loss_streak += 1
        else: self.loss_streak = 0

risk = risk_manager = RiskManager()

# --- 🎯 2. 策略与执行配置 ---
TRADES_LOG = "trades.json"
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, 
    "max_ask": 0.65,
    "bet_amount": 2.0
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s')
logger = logging.getLogger("PolyBot-Final")

def get_trading_client():
    try:
        pk, ak, sec, pas = os.getenv("POLY_PRIVATE_KEY"), os.getenv("POLY_API_KEY"), os.getenv("POLY_API_SECRET"), os.getenv("POLY_PASSPHRASE")
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
        client.set_api_creds(ak, sec, pas)
        return client
    except: return None

class BinanceStream:
    def __init__(self):
        self.price = 0.0
        self.url = "wss://stream.binance.us:9443/ws/btcusdt@kline_1m"
    async def start(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceStream()

# --- 🔄 3. 主循环 ---
async def arb_worker():
    await asyncio.sleep(5)
    client = get_trading_client()
    if not client: return
    
    while True:
        try:
            # 这里的 100 建议实战换成 client.get_balance()
            can_go, reason = risk.check(100.0)
            if not can_go:
                await asyncio.sleep(60); continue

            if stream.price > TARGET_CONFIG["trigger_p"]:
                _, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask and ask < TARGET_CONFIG["max_ask"]:
                    size = TARGET_CONFIG["bet_amount"] / ask
                    resp = client.create_and_post_order(OrderArgs(price=ask, size=size, side="BUY", token_id=TARGET_CONFIG["token_id"]))
                    if resp.get("success"):
                        order_id = resp.get("orderID")
                        with open(TRADES_LOG, "a") as f:
                            f.write(json.dumps({"t": time.time(), "id": order_id, "p": ask, "profit": -0.01}) + "\n")
                        risk.update(-0.01) # 预减滑点
                        send_telegram_msg(f"✅ 实盘成交! ID: {order_id} | 连亏: {risk.loss_streak}")
                        await asyncio.sleep(300)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Worker Error: {e}"); await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    asyncio.create_task(arb_worker())
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root(): return {"status": "ok", "locked": risk.is_locked, "price": stream.price}

@app.post("/get_trades")
async def get_trades(request: Request):
    req = await request.json()
    if req.get("key") != CONTROL_KEY: return {"error": "403"}, 403
    return FileResponse(TRADES_LOG) if os.path.exists(TRADES_LOG) else {"msg": "no trades"}

@app.post("/control")
async def control(request: Request):
    req = await request.json()
    if req.get("key") != CONTROL_KEY: return {"status": "deny"}
    cmd = req.get("cmd")
    if cmd == "STOP": risk.is_locked = True; return {"msg": "🚫 机器人已紧急停火"}
    if cmd == "START": risk.is_locked = False; risk.daily_loss = 0; risk.loss_streak = 0; return {"msg": "🟢 机器人已重置重启"}
    return {"status": "unknown"}
    
# ... (保持 root 和 get_trades 接口不变) ...
