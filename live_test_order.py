"""
Polymarket 真实试单 - $5 限价单
策略：找当前 BTC 5分钟市场，根据 Binance 实时价格方向买入胜算更高的一侧
"""
import requests
import time
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON

load_dotenv()

HOST = 'https://clob.polymarket.com'
GAMMA_API = 'https://gamma-api.polymarket.com'

pk = os.getenv('WALLET_PRIVATE_KEY').replace('0x', '')
creds = ApiCreds(
    api_key=os.getenv('POLY_API_KEY'),
    api_secret=os.getenv('POLY_API_SECRET'),
    api_passphrase=os.getenv('POLY_API_PASSPHRASE')
)
client = ClobClient(HOST, key=pk, chain_id=POLYGON, creds=creds)

TRADE_AMOUNT = 5.0   # 每笔 $5，不超过 $10 上限
MAX_TRADE = 10.0

print("=" * 55)
print("  Polymarket 真实试单 (最大 $10 / 笔)")
print("=" * 55)

# ── 1. 获取当前 BTC 5分钟市场 ─────────────────────────────
now = int(time.time())
window_start = (now // 300) * 300
window_end = window_start + 300
event_slug = f'btc-updown-5m-{window_start}'
remaining = window_end - now

print(f"\n当前时间: {datetime.now().strftime('%H:%M:%S')}")
print(f"5分钟窗口: {datetime.fromtimestamp(window_start).strftime('%H:%M')} → {datetime.fromtimestamp(window_end).strftime('%H:%M')}")
print(f"窗口剩余: {remaining} 秒")

# 如果剩余时间不足 30 秒，等下一个窗口
if remaining < 30:
    print(f"⏳ 剩余时间不足 30 秒，等待下一个窗口...")
    time.sleep(remaining + 5)
    now = int(time.time())
    window_start = (now // 300) * 300
    window_end = window_start + 300
    event_slug = f'btc-updown-5m-{window_start}'
    remaining = window_end - now
    print(f"新窗口: {datetime.fromtimestamp(window_start).strftime('%H:%M')} → {datetime.fromtimestamp(window_end).strftime('%H:%M')}")

r = requests.get(f'{GAMMA_API}/events?slug={event_slug}', timeout=10)
events = r.json()

if not events:
    print(f"❌ 未找到市场: {event_slug}")
    exit(1)

market = events[0]['markets'][0]
token_ids = json.loads(market['clobTokenIds'])
up_token_id = token_ids[0]    # Up
down_token_id = token_ids[1]  # Down
prices = json.loads(market['outcomePrices'])
up_price = float(prices[0])
down_price = float(prices[1])

print(f"\n✅ 市场: {market['question']}")
print(f"   Up   token: {up_token_id[:30]}... 当前价: ${up_price:.2f}")
print(f"   Down token: {down_token_id[:30]}... 当前价: ${down_price:.2f}")
print(f"   流动性: ${float(market.get('liquidityNum', 0)):.0f}")
print(f"   24h成交量: ${float(market.get('volume24hr', 0)):.0f}")

# ── 2. 获取 Binance BTC 实时价格判断方向 ──────────────────
print("\n── 获取 Binance 实时价格 ──")
try:
    r2 = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=5)
    btc_price = float(r2.json()['price'])
    
    # 获取窗口开始时的价格（用 kline 数据）
    r3 = requests.get(
        'https://api.binance.com/api/v3/klines',
        params={'symbol': 'BTCUSDT', 'interval': '5m', 'limit': 2},
        timeout=5
    )
    klines = r3.json()
    open_price = float(klines[-1][1])  # 当前5分钟K线开盘价
    change_pct = (btc_price - open_price) / open_price * 100
    
    print(f"   当前 BTC 价格: ${btc_price:,.2f}")
    print(f"   本窗口开盘价: ${open_price:,.2f}")
    print(f"   涨跌幅: {change_pct:+.3f}%")
    
    # 判断方向
    if change_pct > 0.02:
        direction = 'Up'
        target_token_id = up_token_id
        target_price = up_price
        print(f"   📈 方向信号: UP (涨幅 {change_pct:+.3f}%)")
    elif change_pct < -0.02:
        direction = 'Down'
        target_token_id = down_token_id
        target_price = down_price
        print(f"   📉 方向信号: DOWN (跌幅 {change_pct:+.3f}%)")
    else:
        # 方向不明确，选价格更低的一侧（赔率更高）
        if up_price < down_price:
            direction = 'Up'
            target_token_id = up_token_id
            target_price = up_price
        else:
            direction = 'Down'
            target_token_id = down_token_id
            target_price = down_price
        print(f"   ⚖️  方向不明确，选价格更低侧: {direction} (${target_price:.2f})")

except Exception as e:
    print(f"   Binance 价格获取失败: {e}")
    # 默认选价格更低的一侧
    if up_price <= down_price:
        direction, target_token_id, target_price = 'Up', up_token_id, up_price
    else:
        direction, target_token_id, target_price = 'Down', down_token_id, down_price

# ── 3. 获取订单簿确认流动性 ───────────────────────────────
print(f"\n── 订单簿检查 ({direction}) ──")
try:
    book = client.get_order_book(target_token_id)
    asks = book.asks[:3] if book and book.asks else []
    bids = book.bids[:3] if book and book.bids else []
    print(f"   最优卖价 (Asks): {[(a.price, a.size) for a in asks]}")
    print(f"   最优买价 (Bids): {[(b.price, b.size) for b in bids]}")
    
    if asks:
        best_ask = float(asks[0].price)
        best_ask_size = float(asks[0].size)
        potential_profit = (1.0 - best_ask) * (TRADE_AMOUNT / best_ask)
        print(f"\n   最优卖价: ${best_ask:.4f}")
        print(f"   可买数量: {TRADE_AMOUNT / best_ask:.2f} tokens")
        print(f"   预期利润: ${potential_profit:.4f} (若方向正确)")
    else:
        best_ask = target_price + 0.01
        print(f"   ⚠️  无卖单，使用市价 + 0.01 = ${best_ask:.4f}")
        
except Exception as e:
    print(f"   订单簿获取失败: {e}")
    best_ask = target_price + 0.01

# ── 4. 成本过滤 ────────────────────────────────────────────
print(f"\n── 成本核算 ──")
# Polymarket 手续费: crypto_fees_v2, rate=0.07, taker only
# Fee = rate * p * (1-p) * size (简化版)
fee_rate = 0.07
fee_estimate = fee_rate * best_ask * (1 - best_ask) * (TRADE_AMOUNT / best_ask)
net_profit = (1.0 - best_ask) * (TRADE_AMOUNT / best_ask) - fee_estimate

print(f"   买入价格: ${best_ask:.4f}")
print(f"   买入金额: ${TRADE_AMOUNT:.2f}")
print(f"   预估手续费: ${fee_estimate:.4f}")
print(f"   预期净利润 (若赢): ${net_profit:.4f}")
print(f"   预期净亏损 (若输): -${TRADE_AMOUNT:.2f}")

if best_ask >= 0.97:
    print(f"\n⚠️  价格过高 (${best_ask:.4f})，利润空间不足，跳过")
    exit(0)

# ── 5. 执行下单 ────────────────────────────────────────────
print(f"\n── 执行下单 ──")
print(f"   方向: {direction}")
print(f"   Token ID: {target_token_id[:40]}...")
print(f"   买入价格: ${best_ask:.4f}")
print(f"   买入金额: ${TRADE_AMOUNT:.2f}")
print(f"   窗口剩余: {window_end - int(time.time())} 秒")

try:
    # 计算买入数量 (size = amount / price)
    size = round(TRADE_AMOUNT / best_ask, 2)
    
    order_args = OrderArgs(
        token_id=target_token_id,
        price=best_ask,
        size=size,
        side='BUY',
    )
    
    signed_order = client.create_order(order_args)
    resp = client.post_order(signed_order, OrderType.FOK)  # Fill-or-Kill
    
    print(f"\n✅ 下单成功！")
    print(f"   订单 ID: {resp.get('orderID', 'N/A')}")
    print(f"   状态: {resp.get('status', 'N/A')}")
    print(f"   成交数量: {resp.get('sizeMatched', 0)}")
    
    # 发送 Telegram 通知
    import requests as req
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    msg = f"""🎯 【龙虾火控系统 - 真实试单】
━━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📊 市场: BTC Up or Down 5m
🎲 方向: {direction}
💵 买入: ${TRADE_AMOUNT:.2f} @ ${best_ask:.4f}
📦 数量: {size:.2f} tokens
🔖 订单ID: {resp.get('orderID', 'N/A')}
📋 状态: {resp.get('status', 'N/A')}
💰 预期净利润(若赢): ${net_profit:.4f}
━━━━━━━━━━━━━━━━━━━━━
🚀 真实交易已执行！"""
    req.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',
             json={'chat_id': CHAT_ID, 'text': msg}, timeout=10)
    print("   📱 Telegram 通知已发送")
    
except Exception as e:
    print(f"\n❌ 下单失败: {e}")
    import traceback
    traceback.print_exc()
