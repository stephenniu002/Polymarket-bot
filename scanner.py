import os
import asyncio
from py_clob_client.client import ClobClient
from telegram import Bot

# ------------------------
# 读取环境变量
# ------------------------
POLY_API_KEY = os.getenv("POLY_API_KEY")
MARKET_IDS = os.getenv("MARKET_IDS", "").split(",")
INVEST_AMOUNT = float(os.getenv("INVEST_AMOUNT", 0.1))
PROFIT_THRESHOLD = float(os.getenv("PROFIT_THRESHOLD", 0.02))
LOSS_THRESHOLD = float(os.getenv("LOSS_THRESHOLD", 0.01))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ------------------------
# 初始化 Telegram Bot
# ------------------------
bot = Bot(token=TELEGRAM_TOKEN)

def send_telegram(msg: str):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    print("[TG]", msg)

# ------------------------
# 初始化 Polymarket ClobClient
# ------------------------
clob = ClobClient(api_key=POLY_API_KEY)

# 存储每个市场最后下单的 order_id
last_orders = {}

# ------------------------
# 下单 / 平仓函数
# ------------------------
async def place_order(market_id: str, side: str, amount: float):
    try:
        order = await clob.place_order(
            market_id=market_id,
            side=side,
            size=amount,
            price=None  # 市价下单
        )
        last_orders[market_id] = order.id
        send_telegram(f"{side} {amount} on {market_id}, order_id={order.id}")
        return order.id
    except Exception as e:
        send_telegram(f"下单失败: {e}")

async def close_order(market_id: str):
    order_id = last_orders.get(market_id)
    if order_id:
        try:
            await clob.cancel_order(order_id)
            send_telegram(f"平仓 order_id={order_id} on {market_id}")
            del last_orders[market_id]
        except Exception as e:
            send_telegram(f"平仓失败: {e}")

# ------------------------
# 市场监听和套利逻辑
# ------------------------
async def monitor_market(market_id: str):
    send_telegram(f"开始监控市场: {market_id}")
    async for update in clob.stream_market(market_id):
        price = update.get("price")
        if price is None:
            continue

        # 简单套利策略：低买高卖
        if price < 0.48 and market_id not in last_orders:
            await place_order(market_id, "BUY", INVEST_AMOUNT)
        elif price > 0.52 and market_id in last_orders:
            await close_order(market_id)

# ------------------------
# 主函数
# ------------------------
async def main():
    send_telegram("Polymarket套利机器人启动 ✅")
    tasks = [monitor_market(mid) for mid in MARKET_IDS]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
