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
    is_running = False  # 初始设为 False，由腾讯云指令开启
    trade_size = 20.0
    last_log = "等待初始化..."
    auth_success = False
    scan_count = 0
    price_sum = 1.0  # 实时 YES+NO 价格总和

state = BotState()
poly_client = None

# --- 2. 鉴权函数 (修正版) ---
def initialize_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if pk.lower().startswith("0x"): pk = pk[2:]
        
        if not pk or len(pk) != 64:
            state.last_log = "❌ 私钥长度需为64位"
            return None

        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        
        # 修正：使用 get_api_key_status 验证
        client.get_api_key_status()
        state.auth_success = True
        state.last_log = "🟢 鉴权成功：系统就绪"
        return client
    except Exception as e:
        state.auth_success = False
        state.last_log = f"❌ 鉴权失败: {str(e)}"
        return None

# --- 3. 核心套利逻辑 ---
async def arbitrage_loop():
    global poly_client
    logger.info("🚀 套利扫描器进入循环...")
    while True:
        if state.is_running and state.auth_success:
            try:
                # 这里填入你的 YES 和 NO 的 Token ID (Polymarket 市场 ID)
                # 示例逻辑：获取行情并对比
                # y_price = poly_client.get_price("YES_ID")
                # n_price = poly_client.get_price("NO_ID")
                # state.price_sum = y_price + n_price
                
                state.scan_count += 1
                # if state.price_sum < 0.985:
                #     logger.info("🔥 发现机会，准备下单！")
            except Exception as e:
                logger.error(f"扫描出错: {e}")
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
    value: str = None

@app.post("/control")
async def control_api(req: ControlReq):
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
        return {"msg": "✅ 扫描已启动"}
    
    elif req.cmd == "stop":
        state.is_running = False
        return {"msg": "🛑 扫描已停止"}

    return {"msg": "unknown_cmd"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
