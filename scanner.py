import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

# Polymarket SDK
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Telegram SDK
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

# --- 1. 日志与基础配置 ---
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("PolyBot")

# 从环境变量获取关键配置
PK = os.getenv("WALLET_PRIVATE_KEY", "").strip().replace("0x", "")
API_KEY = os.getenv("POLY_API_KEY", "").strip()
API_SECRET = os.getenv("POLY_API_SECRET", "").strip()
API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE", "").strip()
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 20))

# --- 2. 客户端初始化逻辑 ---
def get_poly_client():
    if not all([PK, API_KEY, API_SECRET, API_PASSPHRASE]):
        logger.error("❌ 缺失关键环境变量，请检查 Railway 设置！")
        return None
    try:
        client = ClobClient("https://clob.polymarket.com", key=PK, chain_id=POLYGON)
        client.set_api_creds({"key": API_KEY, "secret": API_SECRET, "passphrase": API_PASSPHRASE})
        return client
    except Exception as e:
        logger.error(f"❌ 客户端认证失败: {e}")
        return None

poly_client = get_poly_client()
# 存储发现的机会，防止 Button 数据溢出 (Key: short_id, Value: market_info)
opportunity_cache = {}

# --- 3. 核心对冲策略扫描逻辑 ---
async def arbitrage_scanner(context: ContextTypes.DEFAULT_TYPE):
    if not poly_client: return

    try:
        # 1. 获取所有活跃市场并筛选 ETH 5min
        all_markets = poly_client.get_markets()
        target = next((m for m in all_markets if "eth" in m.get('question','').lower() 
                       and "5 minutes" in m.get('question','').lower() and m.get('active')), None)
        
        if not target:
            logger.info("🔎 扫描中: 未发现活跃的 ETH 5min 市场...")
            return

        # 2. 提取 Token ID
        tokens = {t['outcome']: t['token_id'] for t in target['tokens']}
        y_id, n_id = tokens.get('Yes'), tokens.get('No')
        
        # 3. 获取深度（带异常处理：防止订单簿为空）
        y_book = poly_client.get_order_book(y_id)
        n_book = poly_client.get_order_book(n_id)

        if not (y_book.asks and n_book.asks):
            logger.warning(f"⚠️ 市场 {target['condition_id'][:8]} 订单簿流动性不足，跳过")
            return

        y_ask = float(y_book.asks[0].price)
        n_ask = float(n_book.asks[0].price)
        total_cost = y_ask + n_ask

        # 4. 判定对冲机会 (利润阈值设在 1% 以上，即成本 < 0.99)
        if total_cost < 0.99:
            m_key = f"opt_{target['condition_id'][-6:]}"
            opportunity_cache[m_key] = {"yes": y_id, "no": n_id, "title": target['question']}

            msg = (
                f"🚨 **发现对冲机会!**\n\n"
                f"市场: {target['question']}\n"
                f"YES 卖价: `{y_ask}` | NO 卖价: `{n_ask}`\n"
                f"━━━━━━━━━━━━━━\n"
                f"💰 总成本: **{total_cost:.3f}**\n"
                f"📈 预期利润: **{(1-total_cost)*100:.2f}%**"
            )
            
            keyboard = [[InlineKeyboardButton("🎯 一键对冲下单", callback_data=f"tr|{m_key}")]]
            await context.bot.send_message(chat_id=CHAT_ID, text=msg, 
                                         reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            logger.info(f"✅ 发现机会: {total_cost:.3f}")
        else:
            logger.info(f"📊 监控中: {target['question'][:20]}... 指数: {total_cost:.3f}")

    except Exception as e:
        logger.error(f"⚠️ 扫描器运行异常: {e}")

# --- 4. 按钮点击处理 (下单逻辑 + 滑点保护) ---
async def handle_trade_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, m_key = query.data.split("|")
    data = opportunity_cache.get(m_key)
    
    if not data:
        await query.edit_message_text("❌ 机会已过期或缓存已清理。")
        return

    await query.edit_message_text("⏳ 正在验证价格并执行对冲下单...")

    try:
        # 🛡️ 滑点保护：下单前最后一秒重新查价
        y_price = float(poly_client.get_order_book(data['yes']).asks[0].price)
        n_price = float(poly_client.get_order_book(data['no']).asks[0].price)
        
        if (y_price + n_price) >= 0.998:
            await query.edit_message_text(f"🚫 下单中止：价格已变动({y_price+n_price:.3f})，利润消失。")
            return

        # 执行双向买入
        for tid, p in [(data['yes'], y_price), (data['no'], n_price)]:
            order = poly_client.create_order({
                "price": p, "size": TRADE_SIZE, "side": "BUY", "token_id": tid
            })
            poly_client.post_order(order)
        
        await query.edit_message_text(f"✅ 成功！\n以总价 {y_price+n_price:.3f} 完成对冲。")
        logger.info(f"💰 交易执行成功: {data['title']}")

    except Exception as e:
        await query.edit_message_text(f"❌ 交易执行失败: {e}")
        logger.error(f"下单失败详情: {e}")

# --- 5. 主程序入口 (24/7 运行) ---
async def main():
    if not TG_TOKEN or not CHAT_ID:
        logger.error("❌ 未检测到 Telegram 配置，请检查环境变量！")
        return

    # 初始化机器人应用
    app = ApplicationBuilder().token(TG_TOKEN).build()

    # 注册回调处理器
    app.add_handler(CallbackQueryHandler(handle_trade_click))
    
    # 后台每 8 秒扫描一次 (Polymarket API 限制相对宽松，8s 较安全)
    app.job_queue.run_repeating(arbitrage_scanner, interval=8, first=5)

    logger.info("🚀 机器人已完全启动。正在 24/7 监控 ETH 5min 市场...")

    async def test_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ 收到测试指令！你的 Chat ID 是: {update.message.chat_id}")

# 在 main() 函数里的其他 Handler 后面加上这一行
application.add_handler(CommandHandler("test", test_msg))
    # 启动轮询并保持异步状态
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # 保持循环，防止 Railway 退出
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 机器人已安全关闭")
