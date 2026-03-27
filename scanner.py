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

    # 👇 打印前3个市场看看
    for m in markets[:3]:
        question = m.get("question", "无问题")
        price = m.get("lastTradePrice", "无价格")

        print(f"📊 {question} | 价格: {price}")


print("🚀 scanner started")

while True:
    scan()
    time.sleep(15) os

TELEGRAM_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

def send_telegram(msg):
    if not TELEGRAM_TOKEN:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

def get_markets():
    url = "https://api.polymarket.com/markets"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            print("请求失败:", r.status_code)
            return []

        if not r.text:
            print("返回空数据")
            return []

        return r.json()

    except Exception as e:
        print("获取市场错误:", e)
        return []

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

    print(f"✅ 获取到 {len(markets)} 个市场")
        try:
            yes = float(m.get("outcomes", [])[0]["price"])
            no = float(m.get("outcomes", [])[1]["price"])
            total = yes + no

            if total < 0.98:
                msg = f"套利机会: {m['question']} YES={yes} NO={no} SUM={total}"
                print(msg)
                send_telegram(msg)

        except:
            continue

if __name__ == "__main__":
    while True:
        scan()
        time.sleep(60)
