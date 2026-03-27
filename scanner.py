import os
import asyncio
import logging
from dotenv import load_dotenv

# Polymarket SDK
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Telegram SDK
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- 1. 初始化配置 ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

def get_poly_client():
    pk = os.getenv("WALLET_PRIVATE_KEY").strip().replace("0x", "")
    client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
    creds = {
        "key": os.getenv("POLY_API_KEY"),
        "secret": os.getenv("POLY_API_SECRET"),
        "passphrase": os.getenv("POLY_API_PASSPHRASE")
    }
    client.set_api_creds(creds)
    return client

poly_client = get_poly_client()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 50))

# 用于缓存当前的 Token ID 映射，防止 Button 数据过长
token_cache = {}

# --- 2. 动态获取 ETH 5min 市场 ---
async def fetch_latest_eth_market():
    """搜索最新的 ETH 5分钟波动市场"""
    try:
        # 搜索包含 "Ethereum Price" 和 "5 minutes" 的活动市场
        # 实际 API 调用可能需要通过 Gamma API 过滤，这里使用最通用的搜索逻辑
        markets = poly_client.get_markets() # 或者使用过滤参数
        for m in markets:
            title = m.get('question', '').lower()
            if "eth" in title and "5 minutes" in title and m.get('active'):
                tokens = {t['outcome']: t['token_id'] for t in m['tokens']}
                return {
                    "id": m['condition_id'],
                    "title": m['question'],
                    "yes": tokens.get('Yes'),
                    "no": tokens.get('No')
                }
    except Exception as e:
        logging.error(f"获取市场失败: {e}")
    return None

# --- 3. 对冲扫描策略 (后台 Job) ---
async def strategy_scanner(context: ContextTypes.DEFAULT_TYPE):
    market = await fetch_latest_eth_market()
    if not market: return

    try:
        # 获取价格
        yes_ask = float(poly_client.get_order_book(market['yes']).asks[0].price)
        no_ask = float(poly_client.get_order_book(market['no']).asks[0].price)
        
        total = yes_ask + no_ask
        logging.info(f"扫描中: {market['title'][:20]}... 指数: {total}")

        # 发现套利空间 (YES+NO < 1.0)
        if total < 0.99:
            # 存入缓存供按钮使用
            market_key = f"m_{market['id'][:6]}"
            token_cache[market_key] = market

            text = (
                f"🚨 **ETH 5min 对冲机会!**\n"
                f"市场: {market['title']}\n"
                f"YES: {yes_ask} / NO: {no_ask}\n"
                f"总成本: {total:.3f} | 预期利润: {(1-total)*100:.2f}%"
            )
            
            keyboard = [[InlineKeyboardButton("🎯 一键双向对冲下单", callback_data=f"execute|{market_key}")]]
            await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    except Exception as e:
        pass

# --- 4. 处理按钮下单 ---
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("|")
    if parts[0] == "execute":
        market_key = parts[1]
        market = token_cache.get(market_key)
        
        if not market:
            await query.edit_message_text("❌ 错误：市场数据已过期，请等待下次扫描。")
            return

        await query.edit_message_text(f"⏳ 正在为市场 {market_key} 执行对冲操作...")

        try:
            # 1. 再次获取最新价格防止滑点
            y_ask = float(poly_client.get_order_book(market['yes']).asks[0].price)
            n_ask = float(poly_client.get_order_book(market['no']).asks[0].price)

            if (y_ask + n_ask) > 0.995:
                await query.edit_message_text("❌ 下单中止：价格已变动，不再具有对冲利润。")
                return

            # 2. 依次下单 YES 和 NO
            # 注意：实际下单需调用 client.create_order 后 post_order
            for tid, price in [(market['yes'], y_ask), (market['no'], n_ask)]:
                order = poly_client.create_order({
                    "price": price,
                    "size": TRADE_SIZE,
                    "side": "BUY",
                    "token_id": tid
                })
                poly_client.post_order(order)

            await query.edit_message_text(f"✅ 对冲下单完成！\n买入 YES@{y_ask}, NO@{n_ask}\n总成本: {y_ask+n_ask:.3f}")
        
        except Exception as e:
            await query.edit_message_text(f"❌ 交易执行失败: {str(e)}")

# --- 5. 主程序 ---
async def main():
    token = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()

    # 注册处理器
    app.add_handler(CallbackQueryHandler(handle_button))
    
    # 设定定时扫描任务：每 10 秒一次
    app.job_queue.run_repeating(strategy_scanner, interval=10, first=5)

    print("🚀 机器人已启动，正在监听 ETH 5分钟市场机会...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True: await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
# 在你的 main() 中调用
async def main():
    client = get_client()
    print("✅ 身份认证成功，机器人启动中...")
    await run_arbitrage_logic(client)
