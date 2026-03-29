import os
import asyncio
import json
import time
import logging
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from contextlib import asynccontextmanager

# --- 1. 强化日志系统 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RailwayBot")

# --- 2. 策略引擎类 ---
class StrategyEngine:
    def __init__(self):
        self.min_price, self.max_price = 0.25, 0.65

    def kelly_quarter(self, win_rate, odds, bankroll):
        q = 1 - win_rate
        f = (win_rate * odds - q) / odds
        return max(0, (bankroll * f) / 4)

engine = StrategyEngine()

# --- 3. 生命周期管理 (替代 on_event) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    logger.info("🚀 系统正在初始化...")
    asyncio.create_task(stream.start())
    yield
    # 关闭时执行
    logger.info("🛑 系统正在关闭...")

app = FastAPI(lifespan=lifespan)

# --- 4. 健壮版行情引擎 ---
class BinanceDataStream:
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        self.last_message_time = 0
        self.is_ready = False
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_{self.timeframe}"

    async def start(self):
        try:
            exchange = ccxt_async.binanceus({'enableRateLimit': True, 'timeout': 10000})
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=20)
            temp_df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in temp_df.columns[1:]: temp_df[col] = temp_df[col].astype(float)
            self.df = temp_df
            await exchange.close()
            logger.info("✅ 历史数据加载完成")
        except Exception as e:
            logger.error(f"⚠️ 预热跳过: {e}")
        
        self.is_ready = True
        await self._listen_ws()

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("🟢 Binance.us WS 已连接")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        if not self.df.empty:
                            self.df.iloc[-1, 4] = float(data['c'])
            except Exception as e:
                logger.warning(f"🔄 WS 重连中: {e}")
                await asyncio.sleep(5)

stream = BinanceDataStream()

# --- 5. 路由 ---
@app.get("/")
async def health():
    # 必须秒回，不带任何复杂计算
    return {"status": "ok", "ready": stream.is_ready, "data": len(stream.df)}

@app.get("/strategy/simulate")
async def simulate(p: float = 0.16, price: float = 0.30, bankroll: float = 1260):
    odds = (1 - price) / price
    bet = engine.kelly_quarter(p, odds, bankroll)
    return {"suggested_bet": round(bet, 2), "action": "ENTER" if 0.25 <= price <= 0.65 else "SKIP"}

# --- 6. 生产级启动配置 ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    # 增加超时和存活检测
    uvicorn.run(
        "dashboard:app", 
        host="0.0.0.0", 
        port=port, 
        workers=1, 
        loop="asyncio",
        timeout_keep_alive=30,
        access_log=True
    )
