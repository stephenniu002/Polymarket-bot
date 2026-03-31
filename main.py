import asyncio
import json
import websockets
from collections import deque
from strategy import TailStrategy
from stats import Stats

BINANCE_WS = "wss://stream.binance.com:9443/ws/ethusdt@trade"

BET = 10
MULTIPLIER = 100
TARGET_PUMP = 0.01   # 1% 目标涨幅（关键参数）

strategy = TailStrategy()
stats = Stats()

# 存储未来价格
future_prices = deque()

# 当前等待结算的交易
open_trades = []

async def run():
    async with websockets.connect(BINANCE_WS) as ws:
        print("🟢 已连接 Binance WS")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            price = float(data["p"])

            # 更新策略
            strategy.update_price(price)

            # 存未来价格（最多60秒）
            future_prices.append(price)
            if len(future_prices) > 60:
                future_prices.popleft()

            # -------------------------
            # 1️⃣ 触发交易
            # -------------------------
            if strategy.check_signal():
                print(f"🎯 触发信号 @ {price}")

                trade = {
                    "entry": price,
                    "timer": 60,
                    "resolved": False
                }
                open_trades.append(trade)

            # -------------------------
            # 2️⃣ 处理已有交易（延迟判定）
            # -------------------------
            for trade in open_trades:
                if trade["resolved"]:
                    continue

                trade["timer"] -= 1

                if trade["timer"] <= 0:
                    entry = trade["entry"]

                    max_future = max(future_prices)

                    # 判断是否达到目标涨幅
                    if (max_future - entry) / entry > TARGET_PUMP:
                        profit = BET * MULTIPLIER
                        print(f"✅ 赢！entry={entry:.2f} max={max_future:.2f}")
                    else:
                        profit = -BET
                        print(f"❌ 输！entry={entry:.2f} max={max_future:.2f}")

                    stats.record(profit)
                    trade["resolved"] = True

                    # 输出统计
                    s = stats.summary()

                    print("------ 当前统计 ------")
                    print(f"📊 交易次数: {s['trades']}")
                    print(f"💰 余额: {s['balance']}")
                    print(f"📈 胜率: {s['win_rate']:.2%}")
                    print(f"⚡ ROI: {s['roi']:.2f}")
                    print("----------------------")

asyncio.run(run())

