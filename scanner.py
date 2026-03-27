import time
import requests

def scan():
    url = "https://api.polymarket.com/v1/markets"

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
