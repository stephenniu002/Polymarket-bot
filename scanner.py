import os
import asyncio
import requests
import websockets
import json
from telegram import Bot
from dotenv import load_dotenv

# -----------------------------
# 加载环境变量
# -----------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MIN_INVEST = float(os.getenv("MIN_INVEST", 1))
MAX_INVEST = float(os.getenv("MAX_INVEST", 5))

bot = Bot(token=TELEGRAM_TOKEN)

# -----------------------------
# API & WebSocket 配置
# -----------------------------
MARKETS_URL = "https://gamma-api.polymarket.com/markets?active=true&limit=10"
POLY_WS = "wss://api.polymarket.com/graphql"

# -----------------------------
# 获取最新活跃市场 Asset IDs
# -----------------------------
def fetch_markets():
    try:
        resp = requests.get(MARKETS_URL)
        resp.raise_for_status()
        data = resp.json()  # Gamma API 返回的是列表
        asset_ids = []

        for market in data:
            print("Market:", market.get("title", "N/A"), "| Market ID:", market.get("id"))
            for outcome in market.get("outcomes", []):
                print(" - Outcome:", outcome.get("name", "N/A"), "| Asset ID:", outcome.get("id"))
                asset_ids.append(outcome.get("id"))
        return asset_ids
    except Exception as e:
        print("[⚠️] Fetch markets failed:", e)
        return []

# -----------------------------
# WebSocket Subscription Query
# -----------------------------
subscription_query = {
    "type": "start",
    "id": "1",
    "payload": {
        "query": """
subscription {
  markets(first: 10) {
    id
    question
    outcomes {
      label
      lastTradePrice
    }
  }
}
"""
    }
}

# -----------------------------
# 套利检测函数
# -----------------------------
def check_arbitrage(outcomes):
    if len(outcomes) < 2:
        return None
    yes_price = outcomes[0].get('lastTradePrice', 0)
    no_price = outcomes[1].get('lastTradePrice', 0)
    total = MIN_INVEST
    if yes_price + no_price == 0:
        return None
    yes_stake = total * no_price / (yes_price + no_price)
    no_stake = total * yes_price / (yes_price + no_price)
    guaranteed_payout = min(
        yes_stake / yes_price if yes_price else 0,
        no_stake / no_price if no_price else 0
    )
    profit = guaranteed_payout - total
    if profit > 0:
        return {"yes_stake": yes_stake, "no_stake": no_stake, "profit": profit}
    return None

# -----------------------------
# Telegram 推送函数
# -----------------------------
def notify(msg):
    print(msg)
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("[⚠️] Telegram send failed:", e)

# -----------------------------
# WebSocket 订阅市场
# -----------------------------
async def subscribe_markets():
    try:
        async with websockets.connect(POLY_WS) as ws:
            await ws.send(json.dumps(subscription_query))
            while True:
                resp = await ws.recv()
                data = json.loads(resp)
                markets = data.get("payload", {}).get("data", {}).get("markets", [])
                for m in markets:
                    outcomes = m.get("outcomes", [])
                    arb = check_arbitrage(outcomes)
                    if arb:
                        msg = f"💹 套利机会:\n{m.get('question', 'N/A')}\n{arb}"
                        notify(msg)
    except Exception as e:
        print("[⚠️] WebSocket error:", e)
        await asyncio.sleep(5)
        await subscribe_markets()  # 自动重连

# -----------------------------
# 主程序
# -----------------------------
async def main():
    fetch_markets()  # 启动时抓最新 Asset IDs
    await subscribe_markets()

if __name__ == "__main__":
    asyncio.run(main())
