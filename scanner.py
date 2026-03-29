import os

# 尝试强制指定，如果快连在后台运行，这有时能激活流量捕获
os.environ['HTTP_PROXY'] = "http://127.0.0.1:1080" # 尝试常用默认端口
os.environ['HTTPS_PROXY'] = "http://127.0.0.1:1080"
import pandas as pd
import asyncio
import websockets
import json
import ccxt.async_support as ccxt_async
import time
import logging

logger = logging.getLogger("DataFeed")

class BinanceDataStream:
    """Binance 5分钟 K线流直连网关 & 历史冷启动预热"""
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = time.time()
        exchange = ccxt_async.binance({
    'urls': {
        'api': {
            'public': 'https://api1.binance.com/api/v3', # 尝试 api1, api2 或 api3
        }
    },
    'enableRateLimit': True,
})
        self._ws_task = None

    async def start(self):
        """1. 预热系统：由 CCXT 补齐最近 200 根 K 线，喂饱 EMA200 算力引擎"""
        logger.info(f"⏳ 冷启动：正在拉取 {self.symbol} 历史 200 根 {self.timeframe} K线数据预热指标引擎...")
        exchange = ccxt_async.binance()
        try:
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            self.df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                self.df[col] = self.df[col].astype(float)
            logger.info("✅ 历史数据填装完毕，引擎进入热机状态。")
        except Exception as e:
            logger.error(f"历史数据拉取失败，策略降级: {e}")
        finally:
            await exchange.close()

        """2. 切入长连接：挂载 WebSocket 实时监听流到后台"""
        self._ws_task = asyncio.create_task(self._listen_ws())
        return self

    async def _listen_ws(self):
        while True:
            try:
                logger.info(f"📡 握手连接 Binance WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("🟢 WebSocket 通道建立，开始注入极速跳动资产池...")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time() # 为 MainLoop 心跳异常截断提供证明
                        data = json.loads(msg)
                        kline = data['k']
                        
                        candle_start_time = kline['t']
                        close_price = float(kline['c'])
                        open_price = float(kline['o'])
                        high_price = float(kline['h'])
                        low_price = float(kline['l'])
                        volume = float(kline['v'])

                        if self.df.empty or candle_start_time > self.df.iloc[-1]['timestamp']:
                            new_row = pd.DataFrame([{
                                'timestamp': candle_start_time,
                                'open': open_price, 'high': high_price, 
                                'low': low_price, 'close': close_price, 'volume': volume
                            }])
                            self.df = pd.concat([self.df, new_row], ignore_index=True)
                            if len(self.df) > 500:
                                self.df = self.df.iloc[-500:] # 控制内存泄漏
                        else:
                            self.df.loc[self.df.index[-1], ['close', 'high', 'low', 'volume']] = [
                                close_price, 
                                max(high_price, self.df.iloc[-1]['high']), 
                                min(low_price, self.df.iloc[-1]['low']), 
                                volume
                            ]
            except Exception as e:
                logger.error(f"❌ WebSocket 遭到物理斩断: {e}")
                await asyncio.sleep(5)

    async def get_latest_kline_df(self):
        if len(self.df) < 200:
            return None
        return self.df.copy()

