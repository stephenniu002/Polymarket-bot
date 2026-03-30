import os, json, logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

# --- 🎯 核心配置 ---
CONTROL_KEY = os.getenv("CONTROL_KEY", "88888888")
TRADES_LOG = "trades.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PolyBot")

app = FastAPI()

# 存储机器人运行状态
class BotState:
    is_locked = False

state = BotState()

# --- 🚀 修复点：显式定义 POST 路由 ---

@app.get("/")
async def root():
    """这是 GET 请求，也就是你刚才看到 200 的地方"""
    return {"status": "online", "locked": state.is_locked}

@app.post("/control")
async def control(request: Request):
    """这是 POST 请求，之前报 405 就是因为缺这个"""
    try:
        data = await request.json()
        if data.get("key") != CONTROL_KEY:
            return {"msg": "Forbidden (Key Error)"}, 403
        
        cmd = data.get("cmd")
        if cmd == "STOP":
            state.is_locked = True
            logger.warning("🚫 紧急停火已执行")
            return {"msg": "🚫 机器人已紧急停火"}
        elif cmd == "START":
            state.is_locked = False
            logger.info("🟢 机器人已恢复作战")
            return {"msg": "✅ 机器人已恢复作战"}
        return {"msg": "Unknown Command"}
    except Exception as e:
        return {"msg": f"Error: {str(e)}"}, 500

@app.post("/get_trades")
async def get_trades(request: Request):
    """这同样需要 POST 权限"""
    data = await request.json()
    if data.get("key") != CONTROL_KEY:
        return {"msg": "Forbidden"}, 403
    if os.path.exists(TRADES_LOG):
        return FileResponse(TRADES_LOG)
    return {"msg": "No trades found"}

# 启动命令在 Railway 默认是: uvicorn main:app --host 0.0.0.0 --port $PORT
# 启动命令在 Railway 默认是: uvicorn main:app --host 0.0.0.0 --port $PORT
