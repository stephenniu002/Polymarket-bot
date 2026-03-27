import os
import asyncio
import logging
from dotenv import load_dotenv

# SDK 导入
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- 1. 基础日志 ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

# --- 2. 核心认证 ---
def get_poly_client():
    try:
        pk = os.getenv("WALLET_PRIVATE_KEY", "").strip().replace("0x", "")
        if not pk: return None
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        })
        return client
    except Exception as e:
        logger.error(f"认证失败: {e}")
        return None

poly_client = get_poly_client()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
opportunity_cache = {}

# --- 3. 策略扫描 ---
async def strategy_scanner(context: ContextTypes.DEFAULT_TYPE):
    if not poly_client: return
    try:
        markets = poly_client.get_markets()
        # 寻找活跃的 ETH 市场
        target = next((m for m in markets if "eth" in m.get('question','').lower() and m.get('active')), None)
        
        if target:
            tokens = {t['outcome']: t['token_id'] for t in target['tokens']}
            y_id, n_id = tokens.get('Yes'), tokens.get('No')
            
            # 获取价格
            y_ask = float(poly_client.get_order_book(y_id).asks[0].price)
            n_ask = float(poly_client.get_order_book(n_id).asks[0].price)
            total = y_ask + n_ask
            
            logger.info(f"📊 监控中: {target['question'][:20]} | 指数: {total:.3f}")

            # 测试阶段将阈值设为 1.10 确保能发消息
            if total < 1.10: 
                m_key = f"opt_{target['condition_id'][-6:]}"
                opportunity_cache[m_key] = {"yes": y_id, "no": n_id, "title": target['question']}
                
                text = f"🔔 **行情推送测试**\n市场: {target['question']}\n指数: {total:.3f}\nYES: {y_ask} / NO: {n_ask}"
                kb = [[InlineKeyboardButton("🎯 一键执行对冲", callback_data=f"exec|{m_key}")]]
                await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"扫描异常: {e}")

# --- 4. 处理器 ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ 机器人在线！正在为您监控 ETH 5min 市场...")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ 正在验证价格并准备下单...")
    # 这里可以添加正式下单逻辑

# --- 5. 主程序 ---
async def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or not CHAT_ID:
        logger.error("❌ 环境变量缺失 (TOKEN 或 CHAT_ID)")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    # 每 10 秒运行一次扫描
    app.job_queue.run_repeating(strategy_scanner, interval=10, first=5)

    # 启动确认推送
    try:
        await app.bot.send_message(chat_id=CHAT_ID, text="🚀 **Polymarket 机器人已在 Railway 启动！**\n发送 /start 指令测试。")
    except Exception as e:
        logger.error(f"推送启动消息失败: {e}")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True:
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 机器人已安全关闭")
