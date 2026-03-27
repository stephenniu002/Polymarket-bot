import os
import asyncio
from web3 import Web3
from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport
from telegram import Bot

MIN_INVEST = float(os.getenv("MIN_INVEST", 1))
MAX_INVEST = float(os.getenv("MAX_INVEST", 5))

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
chat_id = os.getenv("TELEGRAM_CHAT_ID")

w3 = Web3(Web3.WebsocketProvider(os.getenv("ETH_WS_URL")))
private_key = os.getenv("WALLET_PRIVATE_KEY")
account_address = Web3.toChecksumAddress(os.getenv("WALLET_ADDRESS"))

transport = WebsocketsTransport(url='wss://api.polymarket.com/graphql')

subscription = gql("""
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
""")

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

def notify(message):
    bot.send_message(chat_id=chat_id, text=message)

def send_trade(amount_usd):
    print(f"💰 执行交易 ${amount_usd}")
    # ⚠️ 这里需要具体合约 ABI / 方法

async def main():
    async with Client(transport=transport, fetch_schema_from_transport=True) as session:
        async for result in session.subscribe(subscription):
            markets = result.get("markets", [])
            for m in markets:
                outcomes = m.get("outcomes", [])
                arb = check_arbitrage(outcomes)
                if arb:
                    msg = f"💹 套利机会: {arb}"
                    print(msg)
                    notify(msg)
                    send_trade(MIN_INVEST)

if __name__ == "__main__":
    print("🚀 Polymarket 套利机器人启动")
    asyncio.run(main())
                    send_telegram(message)
        time.sleep(30)  # 每 30 秒扫描一次

if __name__ == "__main__":
    scan()
