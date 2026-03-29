import os
import asyncio
import json
import time
import logging
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from starlette.responses import JSONResponse

# 1. 极简日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RailwayBot")

# 2. 实例化 FastAPI - 必须在顶层
app = FastAPI()

class BinanceDataStream:
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = 0
        self.is_ready = False
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_{self.timeframe}"

    async def start(self):
        """后台异步启动，绝不阻塞主线程"""
        logger.info(f"⏳ 正在启动数据引擎...")
        
        # 预热历史数据
        try:
            exchange = ccxt_async.binanceus({'enableRateLimit': True, 'timeout': 15000})
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=100)
            self.df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in self.df.columns[1:]: self.df[col] = self.df[col].astype(float)
            await exchange.close()
            logger.info("✅ 历史数据加载完毕")
        except Exception as e:
            logger.error(f"⚠️ 历史数据预热跳过 (可能是网络抖动): {e}")
        
        self.is_ready = True
        # 启动 WebSocket 监听
        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, close_timeout=10) as ws:
                    logger.info("🟢 Binance.us WebSocket 已连接")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        # 简化的数据更新逻辑
                        if not self.df.empty:
                            self.df.iloc[-1, 4] = float(data['c']) 
            except Exception as e:
                logger.warning(f"🔄 WS 重连中: {e}")
                await asyncio.sleep(5)

# 实例化
stream = BinanceDataStream()

@app.on_event("startup")
async def startup_event():
    # 核心：必须使用 create_task，让 startup 瞬间完成！
    asyncio.create_task(stream.start())

@app.get("/")
async def health_check():
    """这是保命接口，必须能快速响应"""
    return {
        "status": "online",
        "ready": stream.is_ready,
        "ts": int(time.time()),
        "data_points": len(stream.df)
    }

@app.get("/data")
async def get_data():
    return stream.df.tail(5).to_dict(orient='records')

# 针对 Railway 的入口保护
if __name__ == "__main__":
    import uvicorn
    # 自动识别端口，Railway 必须
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("dashboard:app", host="0.0.0.0", port=port, workers=1)
