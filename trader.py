import os
from fastapi import FastAPI
from pydantic import BaseModel
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
import asyncio

app = FastAPI()

# 状态管理
class BotState:
    is_active = False
    min_profit = 0.02  # 利润阈值 2%
    trade_amount = 20   # 每次下单 20U

state = BotState()

# --- Polymarket 客户端初始化 ---
def get_client():
    pk = os.getenv("WALLET_PRIVATE_KEY").replace("0x", "")
    client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
    client.set_api_creds({
        "key": os.getenv("POLY_API_KEY"),
        "secret": os.getenv("POLY_API_SECRET"),
        "passphrase": os.getenv("POLY_API_PASSPHRASE")
    })
    return client

# --- 核心对冲逻辑 ---
async def arbitrage_worker():
    client = get_client()
    while True:
        if state.is_active:
            try:
                # 1. 获取目标市场 (以某个 ETH 预测市场为例)
                # 这里的 ID 需要根据具体市场更换
                y_price = float(client.get_order_book("YES_TOKEN_ID").asks[0].price)
                n_price = float(client.get_order_book("NO_TOKEN_ID").asks[0].price)
                
                total_cost = y_price + n_price
                
                # 2. 判断套利空间 (理论上加起来应该等于 1.0)
                if total_cost < (1.0 - state.min_profit):
                    print(f"🔥 发现机会! 成本: {total_cost:.3f}, 预估利润: {1-total_cost:.3f}")
                    # 3. 真实下单：YES 和 NO 各买入指定金额
                    # client.post_order(...) 
                    # 这里为了安全先打 Log，确认逻辑通了再开 post_order
            except Exception as e:
                print(f"❌ 扫描出错: {e}")
        await asyncio.sleep(1) # 高频扫描

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(arbitrage_worker())

# --- 远程控制接口 ---
class CmdReq(BaseModel):
    cmd: str
    key: str
    val: str = None

@app.post("/control")
async def control(req: CmdReq):
    if req.key != os.getenv("CONTROL_KEY"):
        return {"status": "error", "msg": "Key 错误"}
    
    if req.cmd == "start":
        state.is_active = True
        return {"status": "ok", "msg": "⚡ 策略已激活"}
    elif req.cmd == "stop":
        state.is_active = False
        return {"status": "ok", "msg": "🛑 策略已暂停"}
    return {"status": "unknown"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
