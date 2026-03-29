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

# --- 1. 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PolymarketBot")

# --- 2. 实例化 FastAPI (解决 Attribute "app" not found) ---
app = FastAPI()

# --- 3. Binance.us 数据流引擎 ---
class BinanceDataStream:
    """针对美国 IP (Railway) 优化的数据流引擎"""
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = 0
        self.is_ready = False
        
        # 使用 Binance.us 地址，避免 451 错误
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_{self.timeframe}"

    async def start(self):
        logger.info(f"⏳ 正在通过 Binance.us 预热数据: {self.symbol}")
        
        # 实例化 binanceus (CCXT 专用类)
        exchange = ccxt_async.binanceus({
            'enableRateLimit': True,
            'timeout': 30000,
        })

        try:
            # 拉取历史 K 线
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in df.columns[1:]:
                df[col] = df[col].astype(float)
            self.df = df
            self.is_ready = True
            logger.info(f"✅ 历史数据加载成功，记录数: {len(self.df)}")
        except Exception as e:
            logger.error(f"❌ 预热失败: {e}")
            # 即使失败也标记 ready，防止健康检查卡死
            self.is_ready = True 
        finally:
            # 彻底关闭连接，防止 aiohttp 报错
            await exchange.close()

        # 启动实时 WebSocket 监听
        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                logger.info(f"📡 握手 WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("🟢 实时流已接通 (Binance.us)")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        
                        ts, c = data['t'], float(data['c'])
                        
                        # 内存 DataFrame 维护
                        if not self.df.empty and ts > self.df.iloc[-1]['timestamp']:
                            new_row = pd.DataFrame([[
                                ts, float(data['o']), float(data['h']), 
                                float(data['l']), c, float(data['v'])
                            ]], columns=self.df.columns)
                            self.df = pd.concat([self.df, new_row], ignore_index=True).iloc[-500:]
                        elif not self.df.empty:
                            self.df.iloc[-1, 4] = c 
            except Exception as e:
                logger.warning(f"⚠️ WS 断开: {e}，5秒后重试...")
                await asyncio.sleep(5)

# --- 4. 实例化引擎 ---
stream = BinanceDataStream()

# --- 5. FastAPI 路由与生命周期 ---

@app.on_event("startup")
async def startup_event():
    # 异步启动，不阻塞服务器主进程
    asyncio.create_task(stream.start())

@app.get("/")
async def health_check():
    """Railway 健康检查接口 (200 OK)"""
    return {
        "status": "online",
        "engine": "binance.us",
        "ready": stream.is_ready,
        "data_count": len(stream.df),
        "last_update": round(time.time() - stream.last_message_time, 2) if stream.last_message_time > 0 else "N/A"
    }

@app.get("/data")
async def get_latest_data():
    """获取最新 10 条 K 线数据接口"""
    if stream.df.empty:
        return {"msg": "No data yet"}
    return stream.df.tail(10).to_dict(orient='records')

# --- 6. 本地运行入口 ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)sleep(5)
