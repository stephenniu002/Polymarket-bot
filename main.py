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
logger = logging.getLogger("OmniBot")

class BotState:
    is_running = True
    trade_size = float(os.getenv("TRADE_SIZE", 20))
    last_error = "等待初始化..."
    auth_success = False
    scan_count = 0

state = BotState()
poly_client = None

# --- 2. 核心鉴权逻辑 (带清洗与容错) ---
def initialize_poly_client():
    try:
        # 私钥清洗
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if pk.lower().startswith("0x"): pk = pk[2:]
        
        if len(pk) != 64:
            raise ValueError(f"私钥长度错误: {len(pk)}")

        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        
        # 验证账户是否存在及 API 是否有效
        client.get_account()
        state.auth_success = True
        state.last_error = "🟢 鉴权成功，运行中"
        logger.info(state.last_status)
        return client
    except Exception as e:
        state.auth_success = False
        state.last_error = f"❌ 鉴权失败: {str(e)}"
        logger.error(state.last_error)
        return None

# --- 3. 后台扫描任务 ---
async def arbitrage_loop():
    global poly_client
    logger.info("🚀 异步扫描任务已启动")
    while True:
        if state.is_running:
            if not state.auth_success:
                # 如果没过鉴权，每 30 秒后台自动重试一次
                poly_client = initialize_poly_client()
            else:
                try:
                    # 这里放入你的套利扫描逻辑 (ETH 5min 等)
                    state.scan_count += 1
                    # 示例逻辑：logger.info(f"正在执行第 {state.scan_count} 次扫描...")
                    pass
                except Exception as e:
                    logger.error(f"扫描执行异常: {e}")
        
        await asyncio.sleep(10) # 扫描频率

# --- 4. FastAPI 接口 (供腾讯云管理) ---
class ControlReq(BaseModel):
    cmd: str
    key: str
    value: str = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时先尝试初始化一次，但不阻塞 Web 服务
    global poly_client
    poly_client = initialize_poly_client()
    task = asyncio.create_task(arbitrage_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "Online", "auth": state.auth_success, "error": state.last_error}

@app.post("/control")
async def control_api(req: ControlReq):
    # 腾讯云安全 Key 校验
    if req.key != os.getenv("CONTROL_KEY", "88888888"):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if req.cmd == "status":
        return {
            "auth_success": state.auth_success,
            "last_log": state.last_error,
            "trade_size": state.trade_size,
            "scan_count": state.scan_count
        }
    
    elif req.cmd == "set_size":
        state.trade_size = float(req.value)
        return {"msg": f"下单金额已调整为: {state.trade_size}"}

    elif req.cmd == "reauth":
        global poly_client
        poly_client = initialize_poly_client()
        return {"msg": "正在重新发起鉴权...", "result": state.last_error}

    return {"msg": "指令未定义"}

if __name__ == "__main__":
    import uvicorn
    # 兼容 Railway 端口
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.
