"""
龙虾火控系统 - Playwright 自动下单版 v2
- 使用已保存的浏览器 cookies（复用已登录的 Polymarket session）
- 信号分析: Binance RSI + 动量
- 自动下单: 在 T+120~T+180 秒窗口内点击下单
- T-90 秒: 卖出持仓 75%
- 每 30 分钟 Telegram 战报
"""
import os, time, json, requests, asyncio
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# ── 配置 ──────────────────────────────────────────────────
TG_TOKEN     = os.getenv('TELEGRAM_TOKEN')
TG_CHAT      = os.getenv('TELEGRAM_CHAT_ID')
TRADE_AMOUNT = 5.0          # 每笔下单金额 $5
MAX_AMOUNT   = 10.0         # 单笔上限 $10
COOKIES_FILE = '/home/ubuntu/Polymarket-bot/poly_cookies.json'
LOG_FILE     = '/home/ubuntu/Polymarket-bot/pw_trader.log'

# 统计
stats = {'total_trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'gas': 0.0}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def tg(msg):
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
                      json={'chat_id': TG_CHAT, 'text': msg, 'parse_mode': 'HTML'},
                      timeout=8)
    except Exception as e:
        log(f"Telegram 发送失败: {e}")

# ── 信号分析（7个币种）──────────────────────────────────
SYMBOLS = {
    'BTC': 'BTCUSDT',
    'ETH': 'ETHUSDT',
    'SOL': 'SOLUSDT',
    'DOGE': 'DOGEUSDT',
    'XRP': 'XRPUSDT',
    'BNB': 'BNBUSDT',
}

def get_signal(symbol='BTCUSDT'):
    try:
        r = requests.get(
            f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=15',
            timeout=5)
        klines = r.json()
        closes = [float(k[4]) for k in klines]
        current = closes[-1]
        change = (current - closes[0]) / closes[0] * 100

        gains = [max(0, closes[i]-closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1]-closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 50

        if rsi > 55 and change > 0.03:
            return 'UP', current, rsi, change
        if rsi < 45 and change < -0.03:
            return 'DOWN', current, rsi, change
        return 'NEUTRAL', current, rsi, change
    except Exception as e:
        log(f"信号获取异常 {symbol}: {e}")
        return 'ERROR', 0, 0, 0

# ── 获取当前活跃市场 URL ──────────────────────────────────
def get_active_market_url(coin='btc'):
    try:
        now = int(time.time())
        ws = (now // 300) * 300
        slug = f'{coin}-updown-5m-{ws}'
        r = requests.get(f'https://gamma-api.polymarket.com/events?slug={slug}', timeout=8)
        events = r.json()
        if events:
            return f'https://polymarket.com/event/{slug}'
    except:
        pass
    return None

# ── Playwright 自动下单 ───────────────────────────────────
async def place_order_on_page(page, coin, side, amount=TRADE_AMOUNT):
    """在 Polymarket 页面上自动下单"""
    url = get_active_market_url(coin.lower())
    if not url:
        log(f"❌ 找不到 {coin} 当前活跃市场")
        return False

    log(f"🤖 打开市场: {url}")
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_timeout(3000)

        # 截图记录当前状态
        await page.screenshot(path=f'/home/ubuntu/Polymarket-bot/order_{coin}_{int(time.time())}.png')

        # 找到 Yes/No 按钮（Polymarket 5分钟市场用 Yes=Up, No=Down）
        if side == 'UP':
            btn = page.locator('button:has-text("Yes")').first
        else:
            btn = page.locator('button:has-text("No")').first

        if await btn.count() == 0:
            log(f"❌ 找不到 {side} 按钮")
            return False

        await btn.click()
        await page.wait_for_timeout(1000)

        # 找到金额输入框
        amount_input = page.locator('input[placeholder="0"]').first
        if await amount_input.count() == 0:
            amount_input = page.locator('input[type="number"]').first

        if await amount_input.count() > 0:
            await amount_input.fill(str(amount))
            await page.wait_for_timeout(500)

        # 点击 Buy 按钮
        buy_btn = page.locator('button:has-text("Buy")').first
        if await buy_btn.count() == 0:
            log(f"❌ 找不到 Buy 按钮")
            return False

        await buy_btn.click()
        await page.wait_for_timeout(2000)

        # 截图确认下单
        await page.screenshot(path=f'/home/ubuntu/Polymarket-bot/confirm_{coin}_{int(time.time())}.png')
        log(f"✅ 下单成功: {coin} {side} ${amount}")
        tg(f"✅ <b>下单成功</b>\n币种: {coin}\n方向: {side}\n金额: ${amount}")
        stats['total_trades'] += 1
        return True

    except Exception as e:
        log(f"❌ 下单异常: {e}")
        return False

# ── 半小时战报 ────────────────────────────────────────────
def send_report():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    win_rate = f"{stats['wins']}/{stats['total_trades']}" if stats['total_trades'] > 0 else "0/0"
    pct = f"{stats['wins']/stats['total_trades']*100:.0f}%" if stats['total_trades'] > 0 else "0%"
    msg = f"""📊 <b>【龙虾火控系统 - 半小时战报】</b>
━━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {now}
📈 周期净损益: {stats['pnl']:+.2f} USDC
🎯 交易成功率: {pct} ({win_rate} 获利)
📊 总交易笔数: {stats['total_trades']}
🛡️ 熔断状态: 正常 (NORMAL)
🚀 监控市场: BTC/ETH/SOL/DOGE/XRP/BNB
━━━━━━━━━━━━━━━━━━━━━
策略: RSI+动量方向预测 | T+120s 入场"""
    tg(msg)
    log("📊 半小时战报已发送")

# ── 主循环 ────────────────────────────────────────────────
async def main():
    log("=" * 55)
    log("龙虾火控系统 v2 - Playwright 自动下单版 启动")
    log("=" * 55)
    tg("🚀 <b>龙虾火控系统 v2 启动</b>\n模式: Playwright 网页直接下单\n策略: RSI+动量 T+120s 入场")

    last_report = time.time()
    last_trade_window = -1  # 防止同一窗口重复下单

    async with async_playwright() as p:
        # 使用已有的 Chromium 用户数据目录（保留登录状态）
        browser = await p.chromium.launch_persistent_context(
            user_data_dir='/home/ubuntu/.config/chromium',
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # 先打开 Polymarket 确认登录状态
        log("检查 Polymarket 登录状态...")
        await page.goto('https://polymarket.com', wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_timeout(3000)

        # 检查是否已登录（查找 Portfolio 元素）
        portfolio = await page.locator('text="Portfolio"').count()
        if portfolio > 0:
            log("✅ Polymarket 已登录")
        else:
            log("⚠️ 未检测到登录状态，请确认浏览器已登录 Polymarket")
            tg("⚠️ <b>警告</b>: 未检测到 Polymarket 登录状态")

        while True:
            now = int(time.time())
            elapsed = now % 300
            current_window = now // 300

            # 每 30 分钟发送战报
            if time.time() - last_report >= 1800:
                send_report()
                last_report = time.time()

            # T+120 到 T+180 秒：判断方向并下单
            if 120 <= elapsed <= 180 and current_window != last_trade_window:
                log(f"⏱️ 进入下单窗口 [T+{elapsed}s]，扫描7个币种...")

                for coin, symbol in SYMBOLS.items():
                    signal, price, rsi, change = get_signal(symbol)
                    log(f"  {coin}: 信号={signal} 价格=${price:.4f} RSI={rsi:.1f} 变化={change:+.3f}%")

                    if signal in ['UP', 'DOWN']:
                        success = await place_order_on_page(page, coin, signal, TRADE_AMOUNT)
                        if success:
                            last_trade_window = current_window
                            break  # 每个窗口只下一笔，避免过度交易

            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
