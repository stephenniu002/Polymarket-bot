# scanner.py
import os
import time
import json
import requests
from enum import Enum
from dataclasses import dataclass

# --------------------------
# 配置部分（安全读取环境变量）
# --------------------------
POLYMARKET_API = os.getenv("POLYMARKET_API", "https://api.polymarket.com")
CLOB_API_KEY = os.getenv("CLOB_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --------------------------
# 枚举和数据类
# --------------------------
class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

@dataclass
class OrderArgs:
    side: Side
    type: OrderType
    price: float
    size: float

# --------------------------
# 工具函数
# --------------------------
def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 配置未设置，消息不会发送")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram 消息发送失败:", e)

def fetch_markets():
    """获取 Polymarket 市场列表"""
    try:
        resp = requests.get(f"{POLYMARKET_API}/markets")
        return resp.json().get("markets", [])
    except Exception as e:
        print("获取市场失败:", e)
        return []

def fetch_orderbook(market_id: str):
    """获取市场盘口"""
    try:
        resp = requests.get(f"{POLYMARKET_API}/markets/{market_id}/orderbook")
        return resp.json()
    except Exception as e:
        print(f"获取市场 {market_id} 盘口失败:", e)
        return {}

def calculate_arbitrage(orderbook: dict):
    """简单套利逻辑示例"""
    try:
        best_bid = float(orderbook.get("best_bid", 0))
        best_ask = float(orderbook.get("best_ask", 0))
        if best_bid > best_ask:
            profit = best_bid - best_ask
            return {
                "buy": best_ask,
                "sell": best_bid,
                "profit": profit
            }
        return None
    except Exception as e:
        print("计算套利失败:", e)
        return None

# --------------------------
# 主循环
# --------------------------
def main():
    try:
        print("套利扫描器启动...")
        while True:
            markets = fetch_markets()
            for m in markets:
                market_id = m.get("id")
                orderbook = fetch_orderbook(market_id)
                arb = calculate_arbitrage(orderbook)
                if arb:
                    msg = f"市场 {market_id}: 买 {arb['buy']} → 卖 {arb['sell']} (利润 {arb['profit']})"
                    print(msg)
                    send_telegram_message(msg)
            time.sleep(5)  # 每 5 秒扫描一次
    except KeyboardInterrupt:
        print("手动停止")
    except Exception as e:
        print("主循环异常:", e)

if __name__ == "__main__":
    main()
