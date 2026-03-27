import os
import requests
import pandas as pd
from datetime import datetime
from py_clob_client.clob_types import OrderArgs, OrderType  # ClobClient 类型
from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv
import time

# 加载 .env 文件
load_dotenv()

# 获取环境变量
RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 检查环境变量
if not all([RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("请确保 .env 中设置了 RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")

# 初始化 Telegram Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Gamma API URL
MARKETS_URL = "https://gamma-api.polymarket.com/markets"

# 初始化 ClobClient
client = ClobClient(relayer_api_key=RELAYER_API_KEY, private_key=WALLET_PRIVATE_KEY)

def fetch_markets():
    """获取市场数据"""
    resp = requests.get(MARKETS_URL)
    resp.raise_for_status()
    return resp.json()

def detect_arbitrage(markets):
    """检测套利机会"""
    opportunities = []
    for market in markets:
        bids = market.get("bids", [])
        asks = market.get("asks", [])
        if not bids or not asks:
            continue
        best_bid = max(bids)
        best_ask = min(asks)
        if best_bid > best_ask:
            diff = best_bid - best_ask
            opportunities.append({
                "market_id": market["id"],
                "best_bid": best_bid,
                "best_ask": best_ask,
                "profit": diff
            })
    return opportunities

def save_csv(opportunities):
    """保存套利机会到 CSV"""
    if not opportunities:
        return
    df = pd.DataFrame(opportunities)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"arbitrage_{date_str}.csv"
    df.to_csv(filename, index=False)
    print(f"[save_csv] 已保存 CSV: {filename}")

def send_telegram(opportunities):
    """发送套利机会到 Telegram"""
    if not opportunities:
        return
    msg = "💰 套利机会:\n"
    for opp in opportunities:
        msg += f"市场 {opp['market_id']}: 买 {opp['best_ask']} → 卖 {opp['best_bid']} (利润 {opp['profit
