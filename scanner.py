import os
import asyncio
import requests
import json
import pandas as pd
from datetime import datetime
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import orderArgs, orderType
from py_clob_client.order_builder.constants import BUY, SELL
from telegram import Bot
from dotenv import load_dotenv

# -----------------------------
# 加载环境变量
# -----------------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS")
MIN_INVEST = float(os.getenv("MIN_INVEST", 1))
MAX_INVEST = float(os.getenv("MAX_INVEST", 5))

bot = Bot(token=TELEGRAM_TOKEN)

# -----------------------------
# Polymarket / Gamma 配置
# -----------------------------
MARKETS_URL = "https://gamma-api.polymarket.com/markets"
CLOB_HOST = "https://clob.polymarket.com"

# -----------------------------
# 初始化 CLOB 客户端
# -----------------------------
def get_client():
    client = ClobClient(host=CLOB_HOST, chain_id=137)  # Polygon chain ID
    return client

client = get_client()

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
# 获取最新市场和 Asset IDs
# -----------------------------
def fetch_markets(limit=10):
    try:
        resp = requests.get(f"{MARKETS_URL}?active=true&limit={limit}")
        resp.raise_for_status()
        data = resp.json()  # Gamma API 返回列表
        markets_info = []
        for market in data:
            m = {
                "id": market.get("id"),
                "question": market.get("question"),
                "outcomes": []
            }
            for o in market.get("outcomes", []):
                m["outcomes"].append({
                    "id": o.get("id"),
                    "label": o.get("name"),
                    "lastTradePrice": float(o.get("lastTradePrice", 0))
                })
            markets_info.append(m)
        return markets_info
    except Exception as e:
        print("[⚠️] Fetch markets failed:", e)
        return []

# -----------------------------
# 套利检测
# -----------------------------
def check_arbitrage(outcomes):
    if len(outcomes) < 2:
        return None
    yes_price = outcomes[0]["lastTradePrice"]
    no_price = outcomes[1]["lastTradePrice"]
    if yes_price + no_price == 0:
        return None
    total = MIN_INVEST
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
# 自动下单
# -----------------------------
def place_order(outcome_id, side, price, size):
    try:
        args = orderArgs(
            price=price,
            size=size,
            side=side,
            token_id=outcome_id
        )
        signed_order = client.create_order(args, private_key=PRIVATE_KEY, funder_address=FUNDER_ADDRESS)
        response = client.post_order(signed_order, orderType.GTC)
        return response
    except Exception as e:
        print("[⚠️] Order failed:", e)
        return None

# -----------------------------
# 保存到 CSV
# -----------------------------
def save_csv(markets_info):
    rows = []
    for m in markets_info:
        for o in m["outcomes"]:
            rows.append({
                "market_id": m["id"],
                "question": m["question"],
                "outcome_id": o["id"],
                "label": o["label"],
                "price": o["lastTradePrice"],
                "timestamp": datetime.now().isoformat()
            })
    df = pd.DataFrame(rows)
    today = datetime.now().strftime("%Y-%m-%d")
    csv_file = f"markets_{today}.csv"
    df.to_csv(csv_file, index=False)
    print(f"[✅] Saved CSV: {csv_file}")

# -----------------------------
# 主循环
# -----------------------------
async def main_loop():
    while True:
        markets_info = fetch_markets(limit=10)
        if markets_info:
            save_csv(markets_info)
            for m in markets_info:
                arb = check_arbitrage(m["outcomes"])
                if arb:
                    msg = f"💹 套利机会:\n{m['question']}\n{arb}"
                    notify(msg)
                    # 自动下单 (示例：买第一个 outcome 的 yes, 第二个 outcome 的 no)
                    place_order(
                        outcome_id=m["outcomes"][0]["id"],
                        side=BUY,
                        price=m["outcomes"][0]["lastTradePrice"],
                        size=arb["yes_stake"]
                    )
                    place_order(
                        outcome_id=m["outcomes"][1]["id"],
                        side=SELL,
                        price=m["outcomes"][1]["lastTradePrice"],
                        size=arb["no_stake"]
                    )
        await asyncio.sleep(60)  # 每分钟拉取一次，可修改

# -----------------------------
# 启动
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main_loop())
