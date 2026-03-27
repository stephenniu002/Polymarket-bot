import requests
import time
import os

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
    headers = {"Accept": "application/json"}
    r = requests.get(url, headers=headers)
    return r.json()

def scan():
    markets = get_markets()
    for m in markets:
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
