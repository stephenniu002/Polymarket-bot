import time
import requests

def scan():
    url = "https://api.polymarket.com/markets"

    try:
        response = requests.get(url)
        response.raise_for_status()
        markets = response.json()
    except Exception as e:
        print("❌ 获取 markets 失败:", e)
        return

    if not markets:
        print("⚠️ 没有市场数据")
        return

    print(f"✅ 市场数量: {len(markets)}")

    for m in markets[:3]:
        question = m.get("question", "无问题")
        price = m.get("lastTradePrice", "无价格")

        print(f"📊 {question} | 价格: {price}")


print("🚀 scanner started")

while True:
    scan()
    time.sleep(15)
[27/3/2026 上午12:27] No one Newton: import time
import requests


def scan():
    url = "https://api.polymarket.com/markets"

    try:
        response = requests.get(url)
        response.raise_for_status()
        markets = response.json()
    except Exception as e:
        print("❌ 获取 markets 失败:", e)
        return

    if not markets:
        print("⚠️ 没有市场数据")
        return

    print("====================================")
    print(f"✅ 市场数量: {len(markets)}")

    count = 0

    for m in markets:
        question = m.get("question", "无问题")
        price = m.get("lastTradePrice", "无价格")

        print(f"📊 {question} | 价格: {price}")

        count += 1
        if count >= 3:
            break


def main():
    print("🚀 scanner started")

    while True:
        scan()
        time.sleep(15)


if __name__ == "__main__":
    main()
