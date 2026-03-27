import os
import requests
import pandas as pd
from datetime import datetime
import time
import logging

from py_clob_client.clob_types import OrderArgs, OrderType, Side
from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("缺少环境变量！请在 Railway Variables 中设置所有密钥")

# 初始化客户端
bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = ClobClient(
    host="https://clob.polymarket.com",
    relayer_api_key=RELAYER_API_KEY,
    private_key=WALLET_PRIVATE_KEY
)

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets?closed=false&limit=200"

def fetch_active_markets():
    try:
        resp = requests.get(GAMMA_MARKETS_URL, timeout=15)
        resp.raise_for_status()
        markets = resp.json()
        logger.info(f"成功获取 {len(markets)} 个活跃市场")
        return markets
    except Exception as e:
        logger.error(f"获取市场列表失败: {e}")
        return []


def get_orderbook(token_id: str):
    try:
        book = client.get_order_book(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if not bids or not asks:
            return None, None

        best_bid = max(float(b[0] if isinstance(b, (list, tuple)) else b.get("price", 0)) for b in bids)
        best_ask = min(float(a[0] if isinstance(a, (list, tuple)) else a.get("price", 999)) for a in asks)
        return best_bid, best_ask
    except Exception:
        return None, None


def detect_arbitrage(min_profit_pct=0.8):
    markets = fetch_active_markets()
    opportunities = []

    for market in markets:
        try:
            tokens = market.get("clobTokenIds", []) or market.get("tokens", [])
            if len(tokens) < 2:
                continue

            for token_id in tokens[:2]:
                best_bid, best_ask = get_orderbook(token_id)
                if best_bid is None or best_ask is None:
                    continue

                profit = best_bid - best_ask
                profit_pct = (profit / best_ask * 100) if best_ask > 0 else 0

                if profit_pct > min_profit_pct:
                    opportunities.append({
                        "market_id": market.get("id"),
                        "question": market.get("question", "Unknown")[:100],
                        "token_id": token_id,
                        "best_bid": round(best_bid, 6),
                        "best_ask": round(best_ask, 6),
                        "profit": round(profit, 6),
                        "profit_pct": round(profit_pct, 2)
                    })
        except Exception as e:
            logger.warning(f"处理市场出错: {e}")

    opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opportunities


def save_to_csv(opportunities):
    if not opportunities:
        return
    df = pd.DataFrame(opportunities)
    filename = f"arbitrage_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    logger.info(f"已保存 {len(opportunities)} 条记录 → {filename}")


def send_telegram(opportunities):
    if not opportunities:
        return

    msg = "🚨 **Polymarket 套利机会检测** 🚨\n\n"
    for i, opp in enumerate(opportunities[:8], 1):
        msg += f"{i}. **{opp['question']}**\n"
        msg += f"   买入价: {opp['best_ask']} → 卖出价: {opp['best_bid']}\n"
        msg += f"   利润: {opp['profit']} ({opp['profit_pct']}%)\n"
        msg += f"   Token: `{opp['token_id']}`\n\n"

    if len(opportunities) > 8:
        msg += f"... 还有 {len(opportunities)-8} 个机会\n"

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logger.info("Telegram 通知发送成功")
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")


def main():
    logger.info("=== Polymarket 套利机器人已在 Railway 启动 ===")
    
    while True:
        try:
            opportunities = detect_arbitrage(min_profit_pct=0.8)

            if opportunities:
                logger.info(f"发现 {len(opportunities)} 个套利机会！")
                save_to_csv(opportunities)
                send_telegram(opportunities)
            else:
                logger.info("本次扫描未发现符合条件的套利机会")
        except Exception as e:
            logger.error(f"主循环错误: {e}")

        time.sleep(30)


if __name__ == "__main__":
    main()
