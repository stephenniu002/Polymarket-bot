import os
import asyncio
import requests
import websockets
import json
from telegram import Bot

MIN_INVEST = float(os.getenv("MIN_INVEST", 1))
MAX_INVEST = float(os.getenv("MAX_INVEST", 5))

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
chat_id = os.getenv("TELEGRAM_CHAT_ID")

POLY_WS = "wss://api.polymarket.com/graphql"

subscription_query = {
    "type": "start",
    "id": "1",
    "payload": {
        "query": """
        subscription {
          markets(first: 10) {
            id
            question
            outcomes {
              label
              lastTradePrice
            }
          }
        }
        """
    }
}

def check_arbitrage(outcomes):
    if len(outcomes) < 2:
        return None
    yes_price = outcomes[0]['lastTradePrice']
    no_price = outcomes[1]['lastTradePrice']

    total = MIN_INVEST
    yes_stake = total * no_price / (yes_price + no_price)
    no_stake = total * yes_price / (yes_price + no_price)
    guaranteed_payout = min(yes_stake / yes_price, no_stake / no_price)
    profit = guaranteed_payout - total

    if profit > 0:
        return {"yes_stake": yes_stake, "no_stake": no_stake, "profit": profit}
    return None

def notify(msg):
    print(msg)
    bot.send_message(chat_id=chat_id, text=msg)

async def subscribe_markets():
    async with websockets.connect(POLY_WS) as ws:
        await ws.send(json.dumps(subscription_query))
        while True:
            resp = await ws.recv()
            data = json.loads(resp)
            markets = data.get("payload", {}).get("data", {}).get("markets", [])
            for m in markets:
                outcomes = m.get("outcomes", [])
                arb = check_arbitrage(outcomes)
                if arb:
                    msg = f"💹 套利机会:\n{m['question']}\n{arb}"
                    notify(msg)

async def main():
    await subscribe_markets()

if __name__ == "__main__":
    asyncio.run(main())
