import os
import requests
import pandas as pd
from datetime import datetime
from py_clob_client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from telegram import Bot
from dotenv import load_dotenv

# =====================
# 环境变量加载
# =====================
load_dotenv()
RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise Exception("请在 .env 文件中配置所有环境变量")

# =====================
# 初始化 Telegram Bot 和 ClobClient
# =====================
bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = ClobClient(relayer_api_key=RELAYER_API_KEY, private_key=WALLET_PRIVATE_KEY)

# =====================
# Gamma API 地址
# =====================
MARKETS_URL = "https://gamma-api.polymarket.com/markets"

# =====================
# 获取市场数据
# =====================
def fetch_markets():
    resp = requests.get(MARKETS_URL)
    resp.raise_for_status()
    return resp.json()

# =====================
# 套利检测
# =====================
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
            opportunities.append({
                "market_id": market["id"],
                "best_bid": best_bid,
                "best_ask": best_ask,
                "profit": best_bid - best_ask
            })
    return opportunities

# =====================
# 保存 CSV
# =====================
def save_csv(opportunities):
    if not opportunities:
        return
    df = pd.DataFrame(opportunities)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"arbitrage_{date_str}.csv"
    df.to_csv(filename, index=False)
    print(f"[INFO] Saved CSV: {filename}")

# =====================
# Telegram 推送
# =====================
def send_telegram(opportunities):
    if not opportunities:
        print("[INFO] 暂无套利机会")
        return
    msg = "💰 套利机会:\n"
    for opp in opportunities:
        msg += f"市场 {opp['market_id']}: 买 {opp['best_ask']} → 卖 {opp['best_bid']} (利润 {opp['profit']})\n"
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        print("[INFO] Telegram 推送成功")
    except Exception as e:
        print(f"[ERROR] Telegram 推送失败: {e}")

# =====================
# 下单示例
# =====================
def place_order(opportunity):
    try:
        args = OrderArgs(
            market_id=opportunity["market_id"],
            side="buy",  # 可改为 "sell"
            size=1,      # 下单数量
            price=opportunity["best_ask"],
            order_type=OrderType.LIMIT
        )
        order = client.place_order(args)
        print(f"[INFO] 下单成功: {order}")
    except Exception as e:
        print(f"[ERROR] 下单失败: {e}")

# =====================
# 主函数
# =====================
def main():
    print("[INFO] 开始套利检测...")
    markets = fetch_markets()
    opportunities = detect_arbitrage(markets)
    save_csv(opportunities)
    send_telegram(opportunities)
    for opp in opportunities:
        place_order(opp)
    print("[INFO] 执行完成")

# =====================
# 执行
# =====================
if __name__ == "__main__":
    main()
