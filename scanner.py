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
        client = ClobClient("https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds({
            "key": os.getenv("POLY_API_KEY"),
            "secret": os.getenv("POLY_API_SECRET"),
            "passphrase": os.getenv("POLY_API_PASSPHRASE")
        })
        return client
    except: return None

poly_client = get_poly_client()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
opportunity_cache = {}

# --- 3. 策略扫描 (带强制推送测试) ---
async def strategy_scanner(context: ContextTypes.DEFAULT_TYPE):
    if not poly_client: return
    try:
        markets = poly_client.get_markets()
        # 寻找包含 ETH 的活跃市场
        target = next((m for m in markets if "eth" in m.get('question','').lower() and m.get('active')), None)
        
        if target:
            tokens = {t['outcome']: t['token_id'] for t in target['tokens']}
            y_id, n_id = tokens.get('Yes'), tokens.get('No')
            y_ask = float(poly_client.get_order_book(y_id).asks[0].price)
            n_ask = float(poly_client.get_order_book(n_id).asks[0].price)
            total = y_ask + n_ask
            
            logger.info(f"📊 监控中: {target['question'][:20]} | 指数: {total:.3f}")

            # 【测试阶段：阈值调高到 1.10，确保能收到消息】
            if total < 1.10: 
                m_key = f"opt_{target['condition_id'][-6:]}"
                opportunity_cache[m_key] = {"yes": y_id, "no": n_id, "title": target['question']}
                
                text = f"🔔 **发现行情!**\n市场: {target['question']}\n指数: {total:.3f}\nYES: {y_ask} / NO: {n_ask}"
                kb = [[InlineKeyboardButton("🎯 一键下单", callback_data=f"exec|{m_key}")]]
                await context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"扫描出错: {e}")

# --- 4. 指令处理器 ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手动输入 /start 测试连通性"""
    await update.message.reply_text(f"✅ 机器人已连通！你的 ID 是: {update.message.chat_id}\n正在扫描 ETH 5min 市场...")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ 正在尝试执行下单逻辑...")
    # 下单逻辑保持不变...

# --- 5. 主程序 (24/7 稳固版) ---
async def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or not CHAT_ID:
        print("❌ 错误：环境变量缺失")
        return

    # 1. 构建 Application
    app = ApplicationBuilder().token(token).build()

    # 2. 注册处理器
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(handle_button))
    
    # 3. 设定定时任务 (每 10 秒)
    app.job_queue.run_repeating(strategy_scanner, interval=10, first=1)

    # 4. 启动确认：程序启动即发消息
    print("🚀 正在向 Telegram 发送启动确认...")
    try:
        # 直接使用 bot 对象发送一条“上线成功”的消息
        await app.bot.send_message(chat_id=CHAT_ID, text="🚀 **Polymarket 机器人已在 Railway 成功上线！**\n开始实时监控...")
    except Exception as e:
        print(f"❌ 无法发送启动消息，请检查 Token 或 CHAT_ID: {e}")

    # 5. 启动服务
    async with app:
        await app.initialize()
        await app.start()
        # 关键：这里不能直接结束，必须等待轮询
        await app.updater.start_polling()
        print("✅ 轮询已开启，正在监听 /start 指令")
        while True:
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 机器人已安全关闭")
