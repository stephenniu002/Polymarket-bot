import time
import requests

def get_markets():
    # 模拟市场数据
    return [
        {"name": "BTC > 30000 by May", "price": 0.52},
        {"name": "ETH > 2000 in April", "price": 0.48},
        {"name": "XRP > 0.5 in April", "price": 0.45}
    ]

    try:
        response = requests.get(url)
        response.raise_for_status()
        markets = response.json()
    except Exception as e:
        print("❌ 获取 markets 失败:", e)
        return

   markets = get_markets()
if not markets:
    print("没有获取到数据")
    return

for market in markets:
    if market['price'] > 0.5:  # 假设套利条件
        message = f"套利机会: {market['name']} 价格: {market['price']}"
        print(message)
        # 发送 Telegram
        if TELEGRAM_TOKEN and CHAT_ID:
            send_telegram(message)

    print("====================================")
    print(f"✅ 市场数量: {len(markets)}")

    # 只打印前3个市场
    for m in markets[:3]:
        question = m.get("question", "无问题")
        price = m.get("lastTradePrice", "无价格")
        print(f"📊 {question} | 价格: {price}")

def main():
    print("🚀 scanner started")
    while True:
        scan()
        time.sleep(15)

if __name__ == "__main__":
    main()
