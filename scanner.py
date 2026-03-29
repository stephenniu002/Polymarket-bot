import os
import pandas as pd
import asyncio
import websockets
import json
import ccxt.async_support as ccxt_async
import time
import logging

# 只有在本地开发且开启了快连代理端口时才有效
# Railway 环境会自动忽略无法连接的本地端口
LOCAL_PROXY = "http://127.0.0.1:1080" 

logger = logging.getLogger("DataFeed")
logging.basicConfig(level=logging.INFO)

class BinanceDataStream:
    """Binance 5分钟 K线流 - 兼容 Railway 美国部署与本地开发"""
    
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = time.time()
        
        # 自动切换域名：美国服务器建议使用 api1 或 api3
        self.api_endpoint = 'https://api1.binance.com/api/v3'
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.ws_symbol}@kline_{self.timeframe}"
        
        self._ws_task = None
        self.is_running = False

    def _get_proxy_config(self):
        """判断是否需要代理（Railway环境通常不需要，本地环境需要）"""
        # 如果在 Railway 上运行，RAILWAY_ENVIRONMENT 变量通常存在
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            return None
        return {
            'http': LOCAL_PROXY,
            'https': LOCAL_PROXY
        }

    async def start(self):
        """1. 冷启动：拉取历史数据"""
        self.is_running = True
        logger.info(f"⏳ 引擎启动：{self.symbol} ({self.timeframe})")
        
        # 动态配置 CCXT
        exchange_config = {
            'enableRateLimit': True,
            'urls': {'api': {'public': self.api_endpoint}}
        }
        
        proxy = self._get_proxy_config()
        if proxy:
            exchange_config['proxies'] = proxy
            logger.info(f"🌐 检测到本地环境，尝试使用代理: {LOCAL_PROXY}")

        exchange = ccxt_async.binance(exchange_config)
        
        try:
            # 预热 200 根 K 线
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            new_df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                new_df[col] = new_df[col].astype(float)
            self.df = new_df
            logger.info(f"✅ 历史数据加载完成，当前记录: {len(self.df)} 条")
        except Exception as e:
            logger.error(f"❌ 历史数据拉取失败 (403可能是地域限制): {e}")
        finally:
            await exchange.close()

        # 2. 开启实时 WebSocket 监听
        self._ws_task = asyncio.create_task(self._listen_ws())
        return self

    async def _listen_ws(self):
        while self.is_running:
            try:
                logger.info(f"📡 正在连接 WebSocket: {self.ws_url}")
                # 注意：websockets 库默认会读取系统环境变量 HTTP_PROXY
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    logger.info("🟢 WebSocket 已连接，实时数据注入中...")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)
                        k = data['k']
                        
                        # 提取 K 线数据
                        ts, o, h, l, c, v = k['t'], float(k['o']), float(k['h']), float(k['l']), float(k['c']), float(k['v'])

                        if self.df.empty or ts > self.df.iloc[-1]['timestamp']:
                            # 新增一行
                            new_row = pd.DataFrame([[ts, o, h, l, c, v]], columns=self.df.columns)
                            self.df = pd.concat([self.df, new_row], ignore_index=True)
                            if len(self.df) > 500:
                                self.df = self.df.iloc[-500:].reset_index(drop=True)
                        else:
                            # 更新当前行
                            last_idx = self.df.index[-1]
                            self.df.loc[last_idx, ['close', 'high', 'low', 'volume']] = [
                                c, max(h, self.df.loc[last_idx, 'high']), 
                                min(l, self.df.loc[last_idx, 'low']), v
                            ]
            except Exception as e:
                logger.warning(f"⚠️ WebSocket 断开 (可能是403或网络波动): {e}，5秒后重试...")
                await asyncio.sleep(5)

    async def get_latest_kline_df(self):
        """安全获取数据副本，防止计算指标时数据正在写入导致崩溃"""
        if self.df.empty or len(self.df) < 200:
            return None
        return self.df.copy()

# --- 重要：针对 Railway 健康检查的修复方案 ---
# 请确保你的 FastAPI 主文件 (dashboard.py) 包含类似以下内容：
"""
from fastapi import FastAPI
app = FastAPI()
data_feed = BinanceDataStream()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(data_feed.start())

@app.get("/")
async def health_check():
    # 这个接口必须存在，否则 Railway 100.64.x.x 的访问报 403 会导致容器被杀
    return {
        "status": "online", 
        "data_points": len(data_feed.df),
        "last_update": time.time() - data_feed.last_message_time
    }
"""
