import os
import requests
import pandas as pd
from datetime import datetime
import time
import logging

from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("请在 Railway Variables 中设置所有环境变量")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = ClobClient(
    host="https://clob.polymarket.com",
    relayer_api_key=RELAYER_API_KEY,
    private_key=WALLET_PRIVATE_KEY
)

# 使用官方推荐的 /events 接口
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"

def fetch_active_events(max_retries=5):
    """获取活跃 Events（推荐方式）"""
    for attempt in range(max_retries):
        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100,
                "order": "volume_24hr",
                "ascending": "false"
            }

            resp = requests.get(GAMMA_EVENTS_URL, params=params, timeout=25)
            
            logger.info(f"尝试 {attempt+1}: 状态码 = {resp.status_code} | URL = {resp.url}")

            if resp.status_code != 200:
                logger.error(f"HTTP 错误 {resp.status_code}: {resp.text[:400]}")
                time.sleep((attempt + 1) * 5)
                continue

            if not resp.text.strip():
                logger.error("响应内容为空")
                time.sleep((attempt + 1) * 5)
                continue

            events = resp.json()

            if not isinstance(events, list):
                logger.error(f"返回数据不是列表，而是 {type(events)}")
                logger.error(f"响应前300字符: {str(events)[:300]}")
                return []

            logger.info(f"✅ 成功获取 {len(events)} 个活跃 Events")
            return events

        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求异常 (尝试 {attempt+1}): {e}")
        except ValueError as e:   # JSONDecodeError
            logger.error(f"JSON 解析失败 (尝试 {attempt+1}): {e}")
            if 'resp' in locals():
                logger.error(f"响应前500字符: {resp.text[:500]}")
        except Exception as e:
            logger.error(f"未知异常 (尝试 {attempt+1}): {e}")

        time.sleep((attempt + 1) * 6)  # 指数退避

    logger.error("多次重试后仍无法获取市场数据")
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
    except Exception as e:
        logger.debug(f"orderbook 获取失败 {token_id}: {e}")
        return None, None


def detect_arbitrage(min_profit_pct=0.8):
    events = fetch_active_events()
    if not events:
        logger.warning("本次未能获取任何市场数据")
        return []

    opportunities = []
    for event in events:
        try:
            # events 下通常包含 markets
            markets = event.get("markets", [])
            for market in markets:
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
                            "question": event.get("title", "Unknown")[:120],
                            "token_id": token_id,
                            "best_bid": round(best_bid, 6),
                            "best_ask": round(best_ask, 6),
                            "profit": round(profit, 6),
                            "profit_pct": round(profit_pct, 2)
                        })
        except Exception as e:
            logger.warning(f"处理 event 时出错: {e}")

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

    msg = "🚨 **Polymarket 套利机会** 🚨\n\n"
    for i, opp in enumerate(opportunities[:8], 1):
        msg += f"{i}. **{opp['question']}**\n"
        msg += f"   买入: {opp['best_ask']} → 卖出: {opp['best_bid']}\n"
        msg += f"   利润: {opp['profit']} ({opp['profit_pct']}%)\n"
        msg += f"   Token: `{opp['token_id']}`\n\n"

    if len(opportunities) > 8:
        msg += f"... 还有 {len(opportunities)-8} 个\n"

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logger.info("Telegram 通知已发送")
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")


def main():
    logger.info("=== Polymarket 套利机器人启动（使用 /events 接口） ===")

    while True:
        try:
            opportunities = detect_arbitrage(min_profit_pct=0.8)

            if opportunities:
                logger.info(f"发现 {len(opportunities)} 个套利机会！")
                save_to_csv(opportunities)
                send_telegram(opportunities)
            else:
                logger.info("本次未发现符合阈值的套利机会")
        except Exception as e:
            logger.error(f"主循环异常: {e}")

        time.sleep(45)   # 每45秒一次，相对温和


if __name__ == "__main__":
    main()
