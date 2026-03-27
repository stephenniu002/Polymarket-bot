import os
import time
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram 发送失败:", e)

def get_markets():
    # 模拟市场数据
    return [
        {"name": "BTC > 30000 by May", "price": 0.52},
        {"name": "ETH > 2000 in April", "price": 0.48},
        {"name": "XRP > 0.5 in April", "price": 0.45}
    ]

def scan():
    while True:
        markets = get_markets()
        if not markets:
            print("没有获取到数据")
        else:
            for market in markets:
                if market['price'] > 0.5:
                    message = f"套利机会: {market['name']} 价格: {market['price']}"
                    print(message)
                    send_telegram(message)
        time.sleep(30)  # 每 30 秒扫描一次

if __name__ == "__main__":
    scan()
