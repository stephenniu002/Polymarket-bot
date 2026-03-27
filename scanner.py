# scanner.py
import os
import asyncio
import json
from datetime import datetime
import csv
import requests
from dotenv import load_dotenv
from telegram import Bot
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

# -----------------------------
# 加载环境变量
# -----------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RELAYER_API_KEY_ADDRESS = os.getenv("RELAYER_API_KEY_ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
MIN_INVEST = float(os.getenv("MIN_INVEST", 1))
MAX_INVEST = float(os.getenv("MAX_INVEST", 5))
POLY_WS = "wss://api.polymarket.com/graphql"  # 备用 WebSocket（可扩展）
MARKETS_URL = "https://gamma-api.polymarket.com/markets?active=true&limit=10"

bot = Bot(token=TELEGRAM_TOKEN)

# -----------------------------
# 初始化 CLOB 客户端
# -----------------------------
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137  # Polygon
)

# -----------------------------
# 抓取最新市场 Asset IDs
# -----------------------------
def fetch_markets():
    asset_ids = []
    try:
        resp = requests.get(MARKETS_URL)
        resp.raise_for_status()
        data = resp.json()
        for market in data:
            print(f"Market: {market.get('title','N/A')} | ID: {market.get('id')}")
            for outcome in market.get("outcomes", []):
                print(f" - Outcome: {outcome.get('name','N/A')} | Asset ID: {outcome.get('id')}")
                asset_ids.append(outcome.get("id"))
    except Exception as e:
        print("[⚠️] Fetch markets failed:", e)
    return asset_ids

# -----------------------------
# 套利检测
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
# Telegram 推送
# -----------------------------
def notify(msg):
    print(msg)
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("[⚠️] Telegram send failed:", e)

# -----------------------------
# CSV 保存每日套利机会
# -----------------------------
def save_csv(data_list):
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"arbitrage_{today}.csv"
    headers = ["market", "yes_stake", "no_stake", "profit"]
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if f.tell() == 0:  # 文件为空，写入表头
            writer.writeheader()
        for row in data_list:
            writer.writerow(row)

# -----------------------------
# 自动下单
# -----------------------------
def place_order(asset_id, price, size, side="BUY"):
    try:
        order_args = OrderArgs(
            token_id=asset_id,
            price=price,
            size=size,
            side=side,
            address=RELAYER_API_KEY_ADDRESS,
            signature_type=1  # 私钥签名
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)
        print(f"[✅] Order placed: {response}")
        return response
    except Exception as e:
        print(f"[⚠️] Order failed: {e}")
        return None

# -----------------------------
# 主任务循环
# -----------------------------
async def main_loop():
    while True:
        asset_ids = fetch_markets()
        arbitrage_data = []
        for asset_id in asset_ids:
            # 这里简单模拟价格抓取，可扩展为 WebSocket 或 API 实时价格
            outcomes = [
                {"lastTradePrice": 0.51},
                {"lastTradePrice": 0.48}
            ]
            arb = check_arbitrage(outcomes)
            if arb:
                msg = f"💹 套利机会: Asset {asset_id}\n{arb}"
                notify(msg)
                arbitrage_data.append({
                    "market": asset_id,
                    "yes_stake": arb["yes_stake"],
                    "no_stake": arb["no_stake"],
                    "profit": arb["profit"]
                })
                # 自动下单（示例，按套利比例下单）
                place_order(asset_id, price=outcomes[0]["lastTradePrice"], size=arb["yes_stake"], side="BUY")
                place_order(asset_id, price=outcomes[1]["lastTradePrice"], size=arb["no_stake"], side="SELL")
        if arbitrage_data:
            save_csv(arbitrage_data)
        await asyncio.sleep(60)  # 每分钟循环一次

# -----------------------------
# 启动
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main_loop())
