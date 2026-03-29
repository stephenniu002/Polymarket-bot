import os
import asyncio
import json
import time
import logging
import pandas as pd
import websockets
import ccxt.async_support as ccxt_async
from fastapi import FastAPI

# --- 1. 核心配置与日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PolyBot_Pro")

app = FastAPI()

# --- 2. 策略引擎：评分与仓位管理 ---
class StrategyEngine:
    def __init__(self):
        self.alpha, self.beta, self.gamma, self.delta = 0.4, 0.2, 0.2, 0.2
        self.min_price, self.max_price = 0.25, 0.65  # 黄金入场价区间

    def calculate_wallet_score(self, pnl, consistency, specialization, max_dd):
        """
        核心打分公式: S(w) = α·PnL - β·Consistency - γ·Specialization - δ·MaxDD
        """
        score = (self.alpha * pnl) - (self.beta * consistency) - \
                (self.gamma * specialization) - (self.delta * max_dd)
        return round(score, 2)

    def kelly_quarter(self, win_rate, odds, bankroll, max_pos=100):
        """
        保守版凯利公式: f = ((p*b - q) / b) / 4
        win_rate (p): 胜率 (0-1)
        odds (b): 赔率 (例如 0.25买入，赔率是 3)
        """
        q = 1 - win_rate
        f = (win_rate * odds - q) / odds
        suggested_f = max(0, f / 4)  # 四分之一凯利
        
        amount = bankroll * suggested_f
        return min(amount, max_pos)  # 不超过单笔最大仓位

# --- 3. 行情数据引擎 (Binance.us 适配版) ---
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
        logger.info("📡 启动 Binance.us 数据引擎...")
        try:
            exchange = ccxt_async.binanceus({'enableRateLimit': True, 'timeout': 15000})
            ohlcv = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=50)
            self.df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in self.df.columns[1:]: self.df[col] = self.df[col].astype(float)
            await exchange.close()
            logger.info("✅ 历史数据预热完成")
        except Exception as e:
            logger.error(f"⚠️ 预热跳过: {e}")
        
        self.is_ready = True
        asyncio.create_task(self._listen_ws())

    async def _listen_ws(self):
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("🟢 WebSocket 实时流已连接")
                    while True:
                        msg = await ws.recv()
                        self.last_message_time = time.time()
                        data = json.loads(msg)['k']
                        if not self.df.empty:
                            # 仅更新最新价格，保持内存占用极低
                            self.df.iloc[-1, 4] = float(data['c'])
            except Exception as e:
                logger.warning(f"🔄 WS 重连: {e}")
                await asyncio.sleep(5)

# --- 4. 实例化组件 ---
stream = BinanceDataStream()
engine = StrategyEngine()

# --- 5. API 路由 (看板与接口) ---

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(stream.start())

@app.get("/")
async def dashboard_home():
    """主看板：查看机器人生命体征"""
    return {
        "bot_status": "active",
        "market": stream.symbol,
        "engine_ready": stream.is_ready,
        "current_price": stream.df.iloc[-1]['close'] if not stream.df.empty else "Loading...",
        "uptime_ts": int(time.time())
    }

@app.get("/strategy/simulate")
async def simulate_trade(p: float = 0.16, price: float = 0.30, bankroll: float = 1260):
    """
    模拟下单逻辑
    p: 预估胜率 (0.16 代表 16%)
    price: Polymarket 买入价格 (0.30 USD)
    """
    # 计算赔率: b = (1 - price) / price
    odds = (1 - price) / price
    suggested_bet = engine.kelly_quarter(p, odds, bankroll)
    
    return {
        "input": {"win_rate": p, "buy_price": price, "bankroll": bankroll},
        "analysis": {
            "net_odds": round(odds, 2),
            "suggested_bet": round(suggested_bet, 2),
            "risk_level": "Conservative (1/4 Kelly)"
        },
        "verdict": "ENTER" if engine.min_price <= price <= engine.max_price else "SKIP (Price out of range)"
    }

@app.get("/wallet/score")
async def get_wallet_score(pnl: float, dd: float, cons: float = 0.5, spec: float = 0.8):
    """
    计算特定钱包的跟单分数
    """
    score = engine.calculate_wallet_score(pnl, cons, spec, dd)
    return {
        "wallet_score": score,
        "recommendation": "HIGH CONF
