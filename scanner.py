import os
import requests
import pandas as pd
from datetime import datetime
import time
import logging

from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv

# 配置日志（Railway 会自动显示）
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
    raise ValueError("缺少环境变量！请在 Railway Variables 中设置 RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")

# 初始化
bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = ClobClient(
    host="https://clob.polymarket.com",
    relayer_api_key=RELAYER_API_KEY,
    private_key=WALLET_PRIVATE_KEY
)

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"

def fetch_active_markets(max_retries=3):
    """获取活跃市场列表，带重试和详细错误处理"""
    for attempt in range(max_retries):
        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": 150,
                "order": "volume_24hr",
                "ascending": "false"
            }
            resp = requests.get(GAMMA_MARKETS_URL, params=params, timeout=20)
            
            logger.info(f"请求状态码: {resp.status_code} | URL: {resp.url}")
            
            if resp.status_code != 200:
                logger.error(f"HTTP 错误: {resp.status_code} - {resp.text[:300]}")
                time.sleep(5)
                continue

            # 尝试解析 JSON
            markets = resp.json()
            if not isinstance(markets, list):
                logger.error(f"返回数据不是列表: {type(markets)}")
                return []

            logger.info(f"成功获取 {len(markets)} 个活跃市场")
            return markets

        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
        except ValueError as e:  # JSON 解析错误
            logger.error(f"JSON 解析失败 (尝试 {attempt+1}/{max_retries}): {e}")
            logger.error(f"响应内容前200字符: {resp.text[:200] if 'resp' in locals() else '无响应'}")
        except Exception as e:
            logger.error(f"未知错误 (尝试 {attempt+1}/{max_retries}): {e}")

        time.sleep(8)  # 重试间隔

    logger.error("多次尝试后仍无法获取市场数据")
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
        logger.debug(f"获取 orderbook 失败 {token_id}: {e}")
        return None, None


def detect_arbitrage(min_profit_pct=0.8):
    markets = fetch_active_markets()
    if not markets:
        logger.warning("本次未获取到任何市场数据")
        return []

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
                        "question": market.get("question", "Unknown")[:120],
                        "token_id": token_id,
                        "best_bid": round(best_bid, 6),
                        "best_ask": round(best_ask, 6),
                        "profit": round(profit, 6),
                        "profit_pct": round(profit_pct, 2)
                    })
        except Exception as e:
            logger.warning(f"处理单个市场出错: {e}")

    opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opportunities


def save_to_csv(opportunities):
    if not opportunities:
        return
    df = pd.DataFrame(opportunities)
    filename = f"arbitrage_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    logger.info(f"已保存 {len(opportunities)} 条套利记录 → {filename}")


def send_telegram(opportunities):
    if not opportunities:
        return

    msg = "🚨 **Polymarket 套利机会检测** 🚨\n\n"
    for i, opp in enumerate(opportunities[:8], 1):
        msg += f"{i}. **{opp['question']}**\n"
        msg += f"   买入: {opp['best_ask']} → 卖出: {opp['best_bid']}\n"
        msg += f"   利润: {opp['profit']} ({opp['profit_pct']}%)\n"
        msg += f"   Token: `{opp['token_id']}`\n\n"

    if len(opportunities) > 8:
        msg += f"... 还有 {len(opportunities)-8} 个机会\n"

    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logger.info(f"Telegram 已发送 {len(opportunities)} 个机会")
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")


def main():
    logger.info("=== Polymarket 套利机器人已在 Railway 启动 ===")
    logger.info("正在监控市场...（每40秒扫描一次）")

    while True:
        try:
            opportunities = detect_arbitrage(min_profit_pct=0.8)

            if opportunities:
                logger.info(f"发现 {len(opportunities)} 个潜在套利机会！")
                save_to_csv(opportunities)
                send_telegram(opportunities)
            else:
                logger.info("本次扫描未发现符合条件的套利机会")
        except Exception as e:
            logger.error(f"主循环发生严重错误: {e}")

        time.sleep(40)  # 每40秒一次，避免频繁请求被限流


if __name__ == "__main__":
    main()
