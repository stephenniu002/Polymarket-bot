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

# --- 1. 初始化配置 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RailwayBot")

class BotState:
    is_running = True
    trade_size = 20.0
    last_log = "初始化中..."
    auth_success = False
    scan_count = 0

state = BotState()
poly_client = None

# --- 2. 鉴权函数 (容错处理) ---
def initialize_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if pk.lower().startswith("0x"): pk = pk[2:]
        
        # 基础校验
        if not pk or len(pk) != 64:
            state.last_log = "❌ 私钥格式错误"
            return None

        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        
        # 测试 API
        client.get_account()
        state.auth_success = True
        state.last_log = "🟢 鉴权成功，系统就绪"
        return client
    except Exception as e:
        state.auth_success = False
        state.last_log = f"❌ 鉴权失败: {str(e)}"
        return None

# --- 3. 后台循环任务 ---
async def arbitrage_loop():
    global poly_client
    while True:
        if state.is_running:
            if not state.auth_success:
                poly_client = initialize_poly_client()
            else:
                state.scan_count += 1
                # 这里未来放你的套利计算逻辑
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poly_client
    # 启动时执行一次初始化
    poly_client = initialize_poly_client()
    task = asyncio.create_task(arbitrage_loop())
    yield
    task.cancel()

# --- 4. FastAPI 接口 ---
app = FastAPI(lifespan=lifespan)

class ControlReq(BaseModel):
    cmd: str
    key: str
    value: str = None

@app.get("/")
async def health():
    return {"status": "online", "auth": state.auth_success}

@app.post("/control")
async def control_api(req: ControlReq):
    # 安全校验 (建议在 Railway Variables 设置 CONTROL_KEY)
    if req.key != os.getenv("CONTROL_KEY", "88888888"):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if req.cmd == "status":
        return {
            "auth": state.auth_success,
            "log": state.last_log,
            "scans": state.scan_count
        }
    return {"msg": "received"}

# --- 5. 关键：修复 127 行截断问题 ---
if __name__ == "__main__":
    import uvicorn
    # 必须监听 0.0.0.0 和 PORT
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
