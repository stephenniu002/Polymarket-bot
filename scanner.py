import asyncio, os, json, requests, websockets
from dotenv import load_dotenv

load_dotenv()

MARKET_ID = os.getenv("MARKET_ID")
POLY_API_KEY = os.getenv("POLY_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = f"wss://api.polymarket.com/ws?market={MARKET_ID}"
MAX_POSITION = int(os.getenv("MAX_POSITION", 1000))
MAX_TRADE = int(os.getenv("MAX_TRADE", 50))
SPREAD = float(os.getenv("SPREAD", 0.02))

# Telegram 通知
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# 检测套利
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
    resp = requests.post("https://api.clob.polymarket.com/orders", json=payload, headers=headers)
    return resp.json()

# 风控
def check_risk(current_pos, trade_size):
    return current_pos + trade_size <= MAX_POSITION and trade_size <= MAX_TRADE

# 主循环
async def main():
    current_position = 0
    async with websockets.connect(URL) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            yes_price = data.get('yesPrice', 0.5)
            no_price = data.get('noPrice', 0.5)

            if check_arbitrage(yes_price, no_price):
                bid, ask = get_bid_ask(yes_price)
                trade_size = 10
                if check_risk(current_position, trade_size):
                    place_order("buy", bid, trade_size)
                    place_order("sell", ask, trade_size)
                    current_position += trade_size
                    send_telegram(f"下单成功：buy {bid}, sell {ask}")

            await asyncio.sleep(0.1)

asyncio.run(main())
