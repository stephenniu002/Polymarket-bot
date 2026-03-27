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
    "payload
    fetch_markets()  # 启动时抓最新 Asset IDs
    await subscribe_markets()

if __name__ == "__main__":
    asyncio.run(main())
