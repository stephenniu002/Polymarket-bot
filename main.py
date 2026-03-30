import os, asyncio, json, time, logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs

# --- 🎯 1. 核心风控变量 (断路器) ---
class BotState:
    def __init__(self):
        self.is_locked = False  # 紧急停火状态
        self.daily_loss = 0.0
        self.loss_streak = 0
        self.max_daily_loss = -20.0 # 每天亏20刀就停
        self.max_streak = 5 # 连亏5次就停

state = BotState()

# --- 🎯 2. 基础配置 ---
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TRADES_LOG = "trades.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PolyBot")

# --- 🔑 3. 鉴权函数 ---
def get_client():
    try:
        pk = os.getenv("POLY_PRIVATE_KEY")
        ak = os.getenv("POLY_API_KEY")
        as_ = os.getenv("POLY_API_SECRET")
        ps = os.getenv("POLY_PASSPHRASE")
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=137)
        client.set_api_creds(ak, as_, ps)
        return client
    except Exception as e:
        logger.error(f"鉴权配置错误: {e}")
        return None

# --- 🚀 4. 路由接口 (解决 404) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 龙虾哨兵部署成功，等待指令...")
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    status = "🚫 锁定中" if state.is_locked else "🟢 运行中"
    return {"status": status, "daily_loss": state.daily_loss, "streak": state.loss_streak}

@app.post("/control")
async def control(request: Request):
    data = await request.json()
    if data.get("key") != CONTROL_KEY:
        return {"msg": "Forbidden"}, 403
    
    cmd = data.get("cmd")
    if cmd == "STOP":
        state.is_locked = True
        logger.warning("❌ 紧急停火触发！")
        return {"msg": "🚫 机器人已紧急停火"}
    if cmd == "START":
        state.is_locked = False
        state.daily_loss = 0.0
        state.loss_streak = 0
        logger.info("✅ 机器人已重置重启")
        return {"msg": "🟢 机器人已恢复作战"}
    return {"msg": "Unknown Command"}

@app.post("/get_trades")
async def get_trades(request: Request):
    data = await request.json()
    if data.get("key") != CONTROL_KEY:
        return {"msg": "Forbidden"}, 403
    if os.path.exists(TRADES_LOG):
        return FileResponse(TRADES_LOG)
    return {"msg": "暂无成交记录"}
