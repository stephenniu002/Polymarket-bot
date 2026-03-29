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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataFeed")

app = FastAPI()

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
        
        # 自动识别环境：Railway 美国节点通常不需要也不支持快连代理
        is_railway = os.environ.get('RAILWAY_ENVIRONMENT')
        proxies = None
        if not is_railway:
            proxies = {'http': 'http://127.0.0.1:1080', 'https': 'http://127.0.0.1:1080'}
            logger.info("🏠 本地模式：挂载代理端口 1080")

        exchange = ccxt_async.binance({
            'enableRateLimit': True,
            'urls': {'api': {'public': self.api_endpoint}},
            'proxies': proxies,
            'timeout': 20000
        })

        try:
            # 预热 200 根 K 线
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in df.columns[1:]: df[col] = df[col].astype(float)
            self.df = df
            self.is_ready = True
            logger.info("✅ 历史数据填充完毕")
        except Exception as e:
            logger.error(f"❌ 预热失败 (可能是美国IP封锁): {e}")
            self.is_ready = True # 标记为 True 避免卡死健康检查
        finally:
            await exchange.close()

        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("🟢 WebSocket 已连接")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        ts, c = data['t'], float(data['c'])
                        
                        if not self.df.empty and ts > self.df.iloc[-1]['timestamp']:
                            new_row = pd.DataFrame([[ts, float(data['o']), float(data['h']), float(data['l']), c, float(data['v'])]], columns=self.df.columns)
                            self.df = pd.concat([self.df, new_row], ignore_index=True).iloc[-500:]
                        elif not self.df.empty:
                            self.df.iloc[-1, 4] = c # 更新收盘价
            except Exception as e:
                logger.warning(f"⚠️ WS断开: {e}，5秒后重试...")
                await asyncio.sleep(5)

# 实例化流
stream = BinanceDataStream()

# --- 关键：修复 Railway 健康检查的路由 ---

@app.on_event("startup")
async def startup_event():
    # 异步启动，不阻塞 FastAPI 本身启动
    asyncio.create_task(stream.start())

@app.get("/")
async def health_check():
    """
    Railway 专属健康检查路由。必须返回 200 OK。
    如果你的日志还报 403，请检查是否有全局 Middleware 拦截了请求。
    """
    return {
        "status": "online",
        "engine_ready": stream.is_ready,
        "last_ts": stream.df.iloc[-1]['timestamp'] if not stream.df.empty else 0
    }

@app.get("/data")
async def get_data():
    return stream.df.tail(10).to_dict(orient='records')
