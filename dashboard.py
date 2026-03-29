import os, asyncio, json, time, logging
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from contextlib import asynccontextmanager
from py_clob_client.clob_types import OrderArgs
from utils import get_poly_price, send_telegram_msg, get_trading_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot-Live")

# --- 🎯 实盘核心配置 ---
TARGET_CONFIG = {
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b", # 目标市场 YES ID
    "trigger_p": 67000, # 币安价格触发线
    "max_ask": 0.65,    # Poly 买入价上限（超过此价不追）
    "bet_amount": 2.0,  # 单笔测试金额 $2.0 USDC
    "dry_run": True     # 🛡️ 看到鉴权成功日志后，请改为 False 开启实盘
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动行情流
    asyncio.create_task(stream.start())
    # 延迟启动交易引擎
    loop = asyncio.get_event_loop()
    loop.call_later(10, lambda: asyncio.create_task(run_arb_worker()))
    yield

app = FastAPI(lifespan=lifespan)

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
                    logger.info(f"📊 实时比价 | Binance: {stream.price} | Poly Ask: {ask}")
                    
                    # 触发下单逻辑
                    if stream.price > TARGET_CONFIG["trigger_p"] and ask < TARGET_CONFIG["max_ask"]:
                        if TARGET_CONFIG["dry_run"]:
                            logger.warning(f"🧪 [测试信号] 满足买入条件: {ask}")
                        else:
                            logger.info(f"💸 [实盘下单] 正在提交订单: ${TARGET_CONFIG['bet_amount']} @ {ask}")
                            # 执行实盘下单
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
                                send_telegram_msg(f"✅ *实盘下单成功!*\n市场: {TARGET_CONFIG['token_id'][:10]}...\n成交价: {ask}\n订单ID: {order_id}")
                                logger.info(f"✅ 交易成功: {order_id}")
                                await asyncio.sleep(300) # 下单后进入 5 分钟冷却期，防止连环下单
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            await asyncio.sleep(10)

@app.get("/")
async def health(): return {"status": "ok", "p": stream.price}
