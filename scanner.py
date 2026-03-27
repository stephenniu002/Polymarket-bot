import os
import asyncio
import logging
from dotenv import load_dotenv

# Polymarket 官方 SDK
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Telegram SDK
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- 1. 基础配置与日志 ---
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. 核心身份认证函数 ---
def get_poly_client():
    try:
        # 清洗私钥格式
        raw_pk = os.getenv("WALLET_PRIVATE_KEY", "").strip().replace("0x", "")
        if not raw_pk:
            logger.error("❌ 环境变量中未找到 WALLET_PRIVATE_KEY")
            return None
            
        client = ClobClient("https://clob.polymarket.com", key=raw_pk, chain_id=POLYGON)
        
        # 设置 API 凭证
        creds = {
            "key": os.getenv("POLY_API_KEY", "").strip(),
            "secret": os.getenv("POLY_API_SECRET", "").strip(),
            "passphrase": os.getenv("POLY_API_PASSPHRASE", "").strip()
        }
        client.set_api_creds(creds)
        return client
    except Exception as e:
        logger.error(f"❌ 客户端初始化失败: {e}")
        return None

# 初始化全局变量
poly_client = get_poly_client()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 20))
# 用于存储当前发现的机会，防止按钮点击时数据丢失
opportunity_cache = {}

# --- 3. 策略逻辑：动态寻找 ETH 5min 市场并扫描价格 ---
async def strategy_scanner(context: ContextTypes.DEFAULT_TYPE):
    if not poly_client:
        logger.warning("⚠️ 客户端未就绪，跳过本轮扫描")
        return
    
    try:
        # 获取所有活动市场并筛选 ETH 5分钟市场
        # 注意：由于 Polymarket 市场更新极快，动态获取是必须的
        all_markets = poly_client.get_markets()
        target = None
        for m in all_markets:
            title = m.get('question', '').lower()
            if "eth" in title and "5 minutes" in title and m.get('active'):
                target = m
                break
        
        if not target:
            logger.info("🔎 暂未发现活跃的 ETH 5min 市场，等待中...")
            return

        # 提取 Token ID (YES 和 NO)
        tokens = {t['outcome']: t['token_id'] for t in target['tokens']}
        yes_id, no_id = tokens.get('Yes'), tokens.get('No')
        
        # 抓取订单簿最优卖价 (Ask)
        yes_book = poly_client.get_order_book(yes_id)
        no_book = poly_client.get_order_book(no_id)
        
        if yes_book.asks and no_book.asks:
            y_ask = float(yes_book.asks[0].price)
            n_ask = float(no_book.asks[0].price)
            total_index = y_ask + n_ask
            
            logger.info(f"📊 监控: {target['question'][:25]}... | 合计: {total_index:.3f}")

            # 发现对冲盈利空间 (总价 < 0.99)
            if total_index < 0.99:
                m_key = f"opt_{target['condition_id'][:8]}"
                opportunity_cache[m_key] = {
                    "yes": yes_id, "no": no_id, "title": target['question']
                }

                alert_text = (
                    f"🚨 **发现 ETH 5min 对冲套利机会!**\n\n"
                    f"市场: {target['question']}\n"
                    f"🍏 YES 卖价: {y_ask}\n"
                    f"🍎 NO  卖价: {n_ask}\n"
                    f"------------------------\n"
                    f"💰 总成本: {total_index:.3f}\n"
                    f"📈 预期利润: {(1-total_index)*100:.2f}%\n"
                    f"⚖️ 执行规模: ${TRADE_SIZE}"
                )
                
                keyboard = [[InlineKeyboardButton("🚀 一键执行双向对冲", callback_data=f"exec|{m_key}")]]
                await context.bot.send_message(
                    chat_id=CHAT_ID, 
                    text=alert_text, 
                    reply_markup=InlineKeyboardMarkup(keyboard), 
                    parse_mode='Markdown'
                )

    except Exception as e:
        logger.error(f"⚠️ 扫描策略执行异常: {e}")

# --- 4. 按钮点击：执行下单 ---
async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cmd, m_key = query.data.split("|")
    if cmd == "exec":
        data = opportunity_cache.get(m_key)
        if not data:
            await query.edit_message_text("❌ 该机会已过期或缓存已清除。")
            return

        await query.edit_message_text(f"⏳ 正在执行对冲下单 (各 {TRADE_SIZE} 份)...")

        try:
            # 这里的逻辑是同时买入 YES 和 NO
            results = []
            for tid in [data['yes'], data['no']]:
                # 重新获取当前最新价格，防止滑点过大
                current_price = float(poly_client.get_order_book(tid).asks[0].price)
                
                order_args = {
                    "price": current_price,
                    "size": TRADE_SIZE,
                    "side": "BUY",
                    "token_id": tid
                }
                signed_order = poly_client.create_order(order_args)
                resp = poly_client.post_order(signed_order)
                results.append(resp)
            
            await query.edit_message_text(f"✅ 对冲下单成功！\n市场: {data['title'][:30]}...\n请前往 Polymarket 官网查看持仓。")
            logger.info(f"成功执行一次对冲下单: {results}")
            
        except Exception as e:
            await query.edit_message_text(f"❌ 交易执行失败: {str(e)}")
            logger.error(f"下单失败详情: {e}")

# --- 5. 程序入口与存活逻辑 ---
async def main():
    tg_token = os.getenv("TELEGRAM_TOKEN")
    if not tg_token:
        logger.error("❌ 未检测到 TELEGRAM_TOKEN，程序无法启动")
        return

    # 构建 Telegram 应用
    app = ApplicationBuilder().token(tg_token).build()

    # 注册回调处理器
    app.add_handler(CallbackQueryHandler(on_button_click))
    
    # 开启后台定时扫描：每 10 秒运行一次
    app.job_queue.run_repeating(strategy_scanner, interval=10, first=5)

    logger.info("✅ 机器人初始化成功，进入 24/7 监控模式")

    # 启动与保持存活
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # 维持异步循环防止 Railway 关闭容器
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 机器人已正常关闭")
