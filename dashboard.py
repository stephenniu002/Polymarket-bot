import os
import asyncio
import json
import time
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
import logging

logger = logging.getLogger("BinanceUS_Feed")

class BinanceDataStream:
    """切换至 Binance.us 专用流 - 彻底解决美国 IP 451 封锁问题"""
    
    def __init__(self, symbol: str = "BTC/USDT", timeframe: str = '5m'):
        self.symbol = symbol
        # Binance.us 的 symbol 格式通常也是小写连写，例如 btcusdt
        self.ws_symbol = symbol.replace('/', '').lower()
        self.timeframe = timeframe
        self.df = pd.DataFrame()
        self.last_message_time = 0
        self.is_ready = False
        
        # --- 修改点 1: 使用 Binance.us 官方 API 和 WS 地址 ---
        self.api_endpoint = 'https://api.binance.us/api/v3'
        self.ws_url = f"wss://stream.binance.us:9443/ws/{self.ws_symbol}@kline_{self.timeframe}"

    async def start(self):
        logger.info(f"🚀 正在通过 Binance.us 引擎预热: {self.symbol}")
        
        # --- 修改点 2: 使用 ccxt.binanceus 实例化 ---
        # 注意：这里不再需要手动配置 api1/api2 域名，直接用默认的 binanceus 即可
        exchange = ccxt_async.binanceus({
            'enableRateLimit': True,
            'timeout': 30000,
        })

        try:
            # 尝试拉取历史数据
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in df.columns[1:]:
                df[col] = df[col].astype(float)
            self.df = df
            self.is_ready = True
            logger.info(f"✅ Binance.us 历史数据预热成功，当前记录: {len(self.df)}")
        except Exception as e:
            # 如果 binance.us 也失败，通常是由于该交易对不存在（.us 币种较少）
            logger.error(f"❌ Binance.us 预热失败: {e}")
            self.is_ready = True # 保持 ready 状态防止主程序卡死
        finally:
            # --- 修改点 3: 必须显式关闭以消除 aiohttp 资源泄露报错 ---
            await exchange.close()

        # 挂载实时流
        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                logger.info(f"📡 握手 Binance.us WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("🟢 Binance.us 实时流已接通，开始喂入数据...")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        
                        ts, c = data['t'], float(data['c'])
                        
                        # 内存 DataFrame 更新逻辑
                        if not self.df.empty and ts > self.df.iloc[-1]['timestamp']:
                            new_row = pd.DataFrame([[
                                ts, float(data['o']), float(data['h']), 
                                float(data['l']), c, float(data['v'])
                            ]], columns=self.df.columns)
                            self.df = pd.concat([self.df, new_row], ignore_index=True).iloc[-500:]
                        elif not self.df.empty:
                            # 更新当前 K 线
                            self.df.iloc[-1, 4] = c 
            except Exception as e:
                logger.warning(f"⚠️ Binance.us WS 断开: {e}，5秒后尝试重连...")
                await asyncio.sleep(5)
