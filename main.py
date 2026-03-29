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
logger = logging.getLogger("RailwayBot")

class BotState:
    is_running = False  # 初始设为关闭，待腾讯云指令开启
    trade_size = 20.0
    last_log = "等待初始化..."
    auth_success = False
    scan_count = 0
    price_sum = 1.0  # 存储 YES+NO 的价格总和

state = BotState()
poly_client = None

# --- 2. 核心鉴权函数 (兼容性最强版本) ---
def initialize_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if pk.lower().startswith("0x"): pk = pk[2:]
        
        if not pk or len(pk) != 64:
            state.last_log = "❌ 私钥格式错误 (需64位且不带0x)"
            return None

        # 初始化客户端
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        
        # 设置 API 凭证
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        
        # 验证鉴权：获取 API Key 列表，这是最稳健的握手方式
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

# --- 3. 核心套利扫描循环 ---
async def arbitrage_loop():
    global poly_client
    logger.info("🚀 套利任务就绪...")
    while True:
        if state.is_running and state.auth_success:
            try:
                # 这里是未来的计算逻辑：
                # 1. 获取行情 (poly_client.get_price)
                # 2. 计算差价
                # 3. 自动下单 (poly_client.create_order)
                state.scan_count += 1
                state.last_log = f"🟢 运行中：已执行 {state.scan_count} 次扫描"
            except Exception as e:
                logger.error(f"扫描异常: {e}")
                state.last_log = f"⚠️ 扫描出错: {e}"
        await asyncio.sleep(5) # 每 5 秒扫描一次

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poly_client
    # 启动时先初始化
    poly_client = initialize_poly_client()
    task = asyncio.create_task(arbitrage_loop())
    yield
    # 关闭时取消任务
    task.cancel()

# --- 4. FastAPI 控制接口 ---
app = FastAPI(lifespan=lifespan)

class ControlReq(BaseModel):
    cmd: str
    key: str
    value: str = None

@app.get("/")
async def health():
    return {"status": "online", "auth": state.auth_success, "log": state.last_log}

@app.post("/control")
async def control_api(req: ControlReq):
    # 安全校验
    if req.key != os.getenv("CONTROL_KEY", "88888888"):
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if req.cmd == "status":
        return {
            "auth": state.auth_success,
            "running": state.is_running,
            "log": state.last_log,
            "scans": state.scan_count,
            "price_sum": state.price_sum
        }
    
    elif req.cmd == "start":
        state.is_running = True
        return {"msg": "✅ 套利扫描已启动"}
    
    elif req.cmd == "stop":
        state.is_running = False
        return {"msg": "🛑 套利扫描已停止"}

    return {"msg": "未知指令"}

# --- 5. 关键：修复 127 行截断语法错误 ---
if __name__ == "__main__":
    import uvicorn
    # 获取端口，确保引号和括号完全闭合
    server_port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=server_port))
