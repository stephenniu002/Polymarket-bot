import os
import time
import json
import asyncio
import logging
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from starlette.responses import JSONResponse

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Dashboard")

app = FastAPI()

# --- 1. 核心数据流类 ---
class BinanceDataStream:
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = 0
        self.is_ready = False
        
        # 针对美国 IP 优化的备用地址
        self.api_endpoint = 'https://api1.binance.com/api/v3'
        self.ws_url = f"wss://stream.binance.com:443/ws/{self.ws_symbol}@kline_{self.timeframe}"

    async def start(self):
        logger.info(f"🚀 启动数据引擎: {self.symbol}")
        
        # 如果在本地，尝试手动设置代理（快连端口）
        # 如果在 Railway，这段代码会自动忽略无效代理
        proxies = None
        if not os.environ.get('RAILWAY_ENVIRONMENT'):
            proxies = {'http': 'http://127.0.0.1:1080', 'https': 'http://127.0.0.1:1080'}

        exchange = ccxt_async.binance({
            'enableRateLimit': True,
            'urls': {'api': {'public': self.api_endpoint}},
            'proxies': proxies
        })

        try:
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in df.columns[1:]: df[col] = df[col].astype(float)
            self.df = df
            self.is_ready = True
            logger.info("✅ 历史数据填充完毕")
        except Exception as e:
            logger.error(f"❌ 预热失败: {e}")
        finally:
            await exchange.close()

        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("🟢 WebSocket 实时流已连接")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        # 更新/追加逻辑 (简化版)
                        ts, c = data['t'], float(data['c'])
                        if not self.df.empty and ts > self.df.iloc[-1]['timestamp']:
                            new_row = pd.DataFrame([[ts, float(data['o']), float(data['h']), float(data['l']), c, float(data['v'])]], columns=self.df.columns)
                            self.df = pd.concat([self.df, new_row], ignore_index=True).iloc[-500:]
                        elif not self.df.empty:
                            self.df.iloc[-1, 4] = c # 更新收盘价
            except Exception as e:
                logger.warning(f"⚠️ WS断开: {e}，5秒后重试")
                await asyncio.sleep(5)

# 实例化
stream = BinanceDataStream()

# --- 2. 修复 Railway 403 的关键路由 ---

@app.on_event("startup")
async def startup_event():
    # 异步启动数据流，不阻塞服务器启动
    asyncio.create_task(stream.start())

@app.get("/")
async def health_check():
    """
    Railway 健康检查专属接口
    必须返回 200，且不能被中间件拦截
    """
    return {
        "status": "online",
        "engine_ready": stream.is_ready,
        "last_heartbeat": stream.last_message_time,
        "region": os.environ.get('RAILWAY_ENVIRONMENT', 'local_dev')
    }

@app.get("/data")
async def get_data():
    if not stream.is_ready:
        return JSONResponse(status_code=503, content={"msg": "Data warming up..."})
    return stream.df.tail(10).to_dict(orient='records')
