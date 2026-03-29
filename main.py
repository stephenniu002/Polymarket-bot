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

# --- 1. 基础配置 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LobsterBot")

class BotState:
    is_running = False
    auth_success = False
    last_log = "等待初始化..."
    scan_count = 0

state = BotState()
poly_client = None

# --- 2. 核心鉴权函数 (终极稳健版) ---
def initialize_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if pk.lower().startswith("0x"): pk = pk[2:]
        
        # 实例化
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        
        # 注入三段式 API 凭证
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        
        # 核心修正：调用 get_api_keys() (这是目前 SDK 最稳的方法)
        client.get_api_keys()
        
        state.auth_success = True
        state.last_log = "🟢 鉴权成功：系统就绪"
        logger.info(state.last_log)
        return client
    except Exception as e:
        state.auth_success = False
        state.last_log = f"❌ 鉴权失败: {str(e)}"
        logger.error(state.last_log)
        return None

# --- 3. 后台扫描逻辑 ---
async def arbitrage_loop():
    while True:
        if state.is_running and state.auth_success:
            state.scan_count += 1
            # 这里留空，等鉴权通了再写具体的 ETH 扫描逻辑
        await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poly_client
    poly_client = initialize_poly_client()
    task = asyncio.create_task(arbitrage_loop())
    yield
    task.cancel()

# --- 4. FastAPI 接口 ---
app = FastAPI(lifespan=lifespan)

class ControlReq(BaseModel):
    cmd: str
    key: str

@app.post("/control")
async def control_api(req: ControlReq):
    if req.key != os.getenv("CONTROL_KEY", "88888888"):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if req.cmd == "status":
        return {
            "auth": state.auth_success,
            "running": state.is_running,
            "log": state.last_log,
            "scans": state.scan_count
        }
    elif req.cmd == "start":
        state.is_running = True
        return {"msg": "✅ 扫描已启动"}
    elif req.cmd == "stop":
        state.is_running = False
        return {"msg": "🛑 扫描已停止"}
    return {"msg": "unknown_cmd"}

# --- 5. 确保闭合，防止 502 ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
