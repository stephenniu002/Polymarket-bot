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
        msg += f"市场 {opp['market_id']}: 买 {opp['best_ask']} → 卖 {opp['best_bid']} (利润 {opp['profit']})\n"
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        print("[send_telegram] 已发送消息")
    except Exception as e:
        print(f"[send_telegram] 发送失败: {e}")

def place_order(opportunity):
    """下单示例"""
    try:
        args = OrderArgs(
            market_id=opportunity["market_id"],
            side="buy",  # 或 "sell" 根据策略
            size=1,     # 下单数量
            price=opportunity["best_ask"],
            order_type=OrderType.LIMIT
        )
        order = client.place_order(args)
        print(f"[place_order] 下单成功: {order}")
    except Exception as e:
        print(f"[place_order] 下单失败: {e}")

def main_loop(interval=60):
    """主循环，每 interval 秒检测一次"""
    while True:
        try:
            markets = fetch_markets()
            opportunities = detect_arbitrage(markets)
            save_csv(opportunities)
            send_telegram(opportunities)
            for opp in opportunities:
                place_order(opp)
        except Exception as e:
            print(f"[main_loop] 出错: {e}")
        print(f"[main_loop] 等待 {interval} 秒后下一次检测...\n")
        time.sleep(interval)

if __name__ == "__main__":
    main_loop(interval=60)  # 每 60 秒检测一次
