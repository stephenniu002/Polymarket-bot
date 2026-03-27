import os
import requests
import pandas as pd
from datetime import datetime
from py_clob_client.clob_client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType  # 注意大小写
from telegram import Bot
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 初始化 Telegram Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Gamma API URL
MARKETS_URL = "https://gamma-api.polymarket.com/markets"

# 初始化 ClobClient
client = ClobClient(relayer_api_key=RELAYER_API_KEY, private_key=WALLET_PRIVATE_KEY)

def fetch_markets():
    resp = requests.get(MARKETS_URL)
    resp.raise_for_status()
    data = resp.json()
    return data

def detect_arbitrage(markets):
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
    df = pd.DataFrame(opportunities)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"arbitrage_{date_str}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved CSV: {filename}")

def send_telegram(opportunities):
    if not opportunities:
        return
    msg = "💰 套利机会:\n"
    for opp in opportunities:
        msg += f"市场 {opp['market_id']}: 买 {opp['best_ask']} → 卖 {opp['best_bid']} (利润 {opp['profit']})\n"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

def place_order(opportunity):
    try:
        args = OrderArgs(
            market_id=opportunity["market_id"],
            side="buy",  # 或 "sell"，根据策略
            size=1,     # 下单数量，可自行调整
            price=opportunity["best_ask"],
            order_type=OrderType.LIMIT
        )
        order = client.place_order(args)
        print(f"下单成功: {order}")
    except Exception as e:
        print(f"下单失败: {e}")

def main():
    markets = fetch_markets()
    opportunities = detect_arbitrage(markets)
    save_csv(opportunities)
    send_telegram(opportunities)
    for opp in opportunities:
        place_order(opp)

if __name__ == "__main__":
    main()
