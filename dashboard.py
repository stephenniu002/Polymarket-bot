import os, asyncio, json, time, logging
import websockets
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg, get_trading_client

# --- [新增] 交易账本路径 ---
TRADES_LOG = "trades.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Live")

# --- 🎯 实盘核心配置 ---
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b",
    "trigger_p": 67000, 
    "max_ask": 0.65,    
    "bet_amount": 2.0,  
    "dry_run": True,
    "control_key": os.getenv("CONTROL_KEY", "88888888") # 暗号
}

# --- [新增] 记录交易到本地文件 ---
def log_trade(order_data):
    try:
        trades = []
        if os.path.exists(TRADES_LOG):
            with open(TRADES_LOG, "r") as f:
                trades = json.load(f)
        trades.append(order_data)
        with open(TRADES_LOG, "w") as f:
            json.dump(trades[-50:], f) # 只保留最近50条，防止撑爆磁盘
    except Exception as e:
        logger.error(f"账本写入失败: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(stream.start())
    loop = asyncio.get_event_loop()
    loop.call_later(10, lambda: asyncio.create_task(run_arb_worker()))
    yield

app = FastAPI(lifespan=lifespan)

# --- [新增] 给 VPS 龙虾开的“后门” ---
@app.post("/get_trades")
async def get_trades(request: Request):
    data = await request.json()
    if data.get("key") != TARGET_CONFIG["control_key"]:
        return {"error": "暗号不对"}, 403
    if os.path.exists(TRADES_LOG):
        return FileResponse(TRADES_LOG)
    return {"error": "目前没单子"}

# ... (BinanceDataStream 类保持不变) ...
class BinanceDataStream:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol, self.price = symbol, 0.0
        self.ws_url = f"wss://stream.binance.us:9443/ws/{symbol.replace('/','').lower()}@kline_1m"

    async def start(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("🟢 币安 WS 已连接")
                    while True:
                        msg = await ws.recv()
                        self.price = float(json.loads(msg)['k']['c'])
            except: await asyncio.sleep(5)

stream = BinanceDataStream()

async def run_arb_worker():
    logger.info("🔑 正在为 MetaMask 钱包进行 L2 鉴权...")
    client = await asyncio.to_thread(get_trading_client)
    
    if client:
        logger.info("🔥 [核心突破] Polymarket 鉴权成功！实时监控中...")
    else:
        logger.error("❌ [鉴权失败] 请检查私钥(不带0x)和 MATIC 余额")
        return

    while True:
        try:
            if stream.price > 0:
                bid, ask = await asyncio.to_thread(get_poly_price, TARGET_CONFIG["token_id"])
                if ask:
                    # 触发下单逻辑
                    if stream.price > TARGET_CONFIG["trigger_p"] and ask < TARGET_CONFIG["max_ask"]:
                        if TARGET_CONFIG["dry_run"]:
                            logger.warning(f"🧪 [测试信号] 满足买入条件: {ask}")
                        else:
                            logger.info(f"💸 [实盘下单] 正在提交订单: ${TARGET_CONFIG['bet_amount']} @ {ask}")
                            resp = await asyncio.to_thread(
                                client.create_and_post_order,
                                OrderArgs(
                                    token_id=TARGET_CONFIG["token_id"],
                                    price=ask,
                                    size=TARGET_CONFIG["bet_amount"] / ask,
                                    side="BUY"
                                )
                            )
                            if resp.get("success"):
                                order_id = resp.get("orderID")
                                # --- [新增] 下单成功立刻记账 ---
                                log_trade({
                                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "binance": stream.price,
                                    "poly_ask": ask,
                                    "order_id": order_id
                                })
                                send_telegram_msg(f"✅ *实盘下单成功!*\n订单ID: {order_id}")
                                await asyncio.sleep(300) 
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            await asyncio.sleep(10)

@app.get("/")
async def health(): return {"status": "ok", "p": stream.price, "trades_ready": os.path.exists(TRADES_LOG)}
