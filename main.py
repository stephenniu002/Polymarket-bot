import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# SDK 导入
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from telegram import Bot
from telegram.ext import ApplicationBuilder

# --- 1. 初始化与配置 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OmniBot")

# 全局状态控制（由腾讯云远程修改）
class BotState:
    is_running = True
    trade_size = float(os.getenv("TRADE_SIZE", 20))
    scan_interval = 10
    last_status = "初始化中..."

state = BotState()

# --- 2. 核心鉴权函数 ---
def get_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip().replace("0x", "")
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        return client
    except: return None

poly_client = get_poly_client()

# --- 3. 对冲扫描任务 (后台异步运行) ---
async def background_scanner():
    logger.info("🚀 后台扫描任务启动...")
    while True:
        if state.is_running and poly_client:
            try:
                # 模拟扫描逻辑（此处放入你之前的 ETH 5min 扫描代码）
                # 为了简洁，这里仅展示状态更新
                state.last_status = f"正在扫描中... 当前金额: {state.trade_size}"
                # logger.info(state.last_status)
                
                # TODO: 执行具体的 Polymarket 价格检查逻辑
                
            except Exception as e:
                logger.error(f"扫描异常: {e}")
        else:
            state.last_status = "已暂停"
        
        await asyncio.sleep(state.scan_interval)

# --- 4. FastAPI 接口 (供腾讯云调用) ---
class ControlReq(BaseModel):
    cmd: str
    key: str
    value: str = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时开启后台任务
    task = asyncio.create_task(background_scanner())
    yield
    # 关闭时取消任务
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"bot_status": "active", "is_running": state.is_running}

@app.post("/control")
async def control_api(req: ControlReq):
    # 安全校验
    if req.key != os.getenv("CONTROL_KEY", "88888888"):
        raise HTTPException(status_code=403, detail="Key Error")
    
    # 指令处理
    if req.cmd == "status":
        return {"status": state.last_status, "trade_size": state.trade_size}
    
    elif req.cmd == "stop":
        state.is_running = False
        return {"msg": "已停止扫描"}
    
    elif req.cmd == "start":
        state.is_running = True
        return {"msg": "已恢复扫描"}
    
    elif req.cmd == "set_size":
        state.trade_size = float(req.value)
        return {"msg": f"下单金额已修改为: {state.value}"}
    
    return {"msg": "未知指令"}

if __name__ == "__main__":
    import uvicorn
    # Railway 必须监听 PORT 变量
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
