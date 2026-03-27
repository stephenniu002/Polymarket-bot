import asyncio
import os
import json
import requests
from dotenv import load_dotenv

# 1. 修正导入名
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.models import OrderArgs

load_dotenv()

# 环境变量读取
PK = os.getenv("PRIVATE_KEY")
# CLOB 需要这三个凭证（通过 client.create_or_derive_api_creds() 生成）
API_KEY = os.getenv("POLY_API_KEY")
API_SECRET = os.getenv("POLY_API_SECRET")
API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MARKET_ID = os.getenv("MARKET_ID")

# 初始化官方客户端
client = ClobClient(
    host="https://clob.polymarket.com",
    key=PK,
    chain_id=POLYGON
)
# 设置 API 凭证
client.set_api_creds(client.derive_api_creds(API_KEY, API_SECRET, API_PASSPHRASE))

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram通知失败:", e)

# 使用 SDK 下单
def place_order_safe(side, price, size):
    try:
        # 使用 SDK 的创建订单方法（自动处理 EIP-712 签名）
        resp = client.create_order(
            OrderArgs(
                price=price,
                size=size,
                side=side.upper(), # "BUY" or "SELL"
                token_id=MARKET_ID # 注意：这里通常需要 Token ID 而不是 Market ID
            )
        )
        return resp
    except Exception as e:
        send_telegram(f"下单异常: {str(e)}")
        return None

async def main():
    print("正在启动扫描器...")
    # 注意：Polymarket WebSocket 建议使用 SDK 自带的 get_orders 或订阅模式
    # 这里保持你的逻辑框架，但提醒：Market ID 和 Token ID 在下单时是不同的
    
    # 示例逻辑入口...
    # 执行下单时调用：place_order_safe("BUY", 0.45, 10)

if __name__ == "__main__":
    asyncio.run(main())
import requests
import websockets
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

POLY_API_KEY = os.getenv("POLY_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MARKET_ID = os.getenv("MARKET_ID")
MAX_POSITION = int(os.getenv("MAX_POSITION", 1000))
MAX_TRADE = int(os.getenv("MAX_TRADE", 50))
SPREAD = float(os.getenv("SPREAD", 0.02))

# WebSocket URL
WS_URL = f"wss://api.polymarket.com/ws?market={MARKET_ID}"

# Telegram 通知函数
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram通知失败:", e)

# 检测套利机会
def check_arbitrage(yes_price, no_price):
    return yes_price + no_price > 1.01

# 获取挂单价格
def get_bid_ask(yes_price, spread=SPREAD):
    bid = max(yes_price - spread, 0.01)
    ask = min(yes_price + spread, 0.99)
    return bid, ask

# 下单示例（CLOB API）
def place_order(side, price, size):
    headers = {"Authorization": f"Bearer {POLY_API_KEY}"}
    payload = {
        "marketId": MARKET_ID,
        "side": side,
        "price": price,
        "size": size
    }
    try:
        resp = requests.post("https://api.clob.polymarket.com/orders", json=payload, headers=headers)
        return resp.json()
    except Exception as e:
        send_telegram(f"下单失败: {e}")
        return None

# 风控检查
def check_risk(current_pos, trade_size):
    return current_pos + trade_size <= MAX_POSITION and trade_size <= MAX_TRADE

# 主异步函数
async def main():
    current_position = 0
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                print("WebSocket 连接成功")
                async for msg in ws:
                    data = json.loads(msg)
                    yes_price = data.get('yesPrice', 0.5)
                    no_price = data.get('noPrice', 0.5)

                    if check_arbitrage(yes_price, no_price):
                        bid, ask = get_bid_ask(yes_price)
                        trade_size = 10
                        if check_risk(current_position, trade_size):
                            buy_order = place_order("buy", bid, trade_size)
                            sell_order = place_order("sell", ask, trade_size)
                            current_position += trade_size
                            send_telegram(f"下单成功 ✅ 买 {bid}, 卖 {ask}")
        except Exception as e:
            print("WebSocket 连接失败，重试中:", e)
            await asyncio.sleep(5)

# 运行
if __name__ == "__main__":
    asyncio.run(main())
