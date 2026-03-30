import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg

# --- 🛡️ 1. 风控断路器 (核心：防连亏、防爆仓) ---
class RiskManager:
    def __init__(self):
        self.is_locked = False  # 紧急停火状态
        self.daily_loss = 0.0
        self.loss_streak = 0
        self.max_daily_loss = -20.0 
        self.max_streak = 5
        self.last_reset = time.strftime("%Y-%m-%d")

    def check_safe(self):
        if self.is_locked: return False, "🚫 机器人已被手动锁定(STOP)"
        if self.loss_streak >= self.max_streak: return False, "🛑 连亏5场，强制冷静中"
        if self.daily_loss <= self.max_daily_loss: return False, "💸 今日亏损达标，收工"
        return True, "✅ 运行中"

    def update_result(self, profit):
        self.daily_loss += profit
        if profit < 0: self.loss_streak += 1
        else: self.loss_streak = 0

risk = RiskManager()

# --- 🎯 2. 实战配置 ---
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TRADES_LOG = "trades.json"
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, 
    "max_ask": 0.65,
    "bet_amount": 2.0
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PolyBot")

# --- 🚀 3. 核心接口 (修复 404) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动开启监控，这里可以放你的 BinanceStream 和 ArbWorker 逻辑
    logger.info("🔥 龙虾哨兵上线，监听 /control 频道...")
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def status():
    safe, msg = risk.check_safe()
    return {"status": msg, "locked": risk.is_locked, "streak": risk.loss_streak}

# 🚀 修复点：添加控制接口
@app.post("/control")
async def control(request: Request):
    data = await request.json()
    if data.get("key") != CONTROL_KEY:
        return {"msg": "拒绝访问"}, 403
    
    cmd = data.get("cmd")
    if cmd == "STOP":
        risk.is_locked = True
        logger.warning("❌ 接收到远程停火指令！")
        return {"msg": "🚫 机器人已紧急停火"}
    elif cmd == "START":
        risk.is_locked = False
        risk.daily_loss = 0
        risk.loss_streak = 0
        logger.info("🟢 接收到远程复活指令！")
        return {"msg": "✅ 机器人已重启并重置风控"}
    return {"msg": "未知指令"}

@app.post("/get_trades")
async def get_trades(request: Request):
    data = await request.json()
    if data.get("key") != CONTROL_KEY: return {"msg": "403"}, 403
    return FileResponse(TRADES_LOG) if os.path.exists(TRADES_LOG) else {"msg": "暂无成交记录"}
