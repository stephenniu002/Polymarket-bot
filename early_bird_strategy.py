"""
提前布局策略 v2 (Early Bird Strategy)
─────────────────────────────────────────────
时间轴：
  T+0        窗口开始
  T+120~240  第2~4分钟：RSI+动量决策，入场
  T-60       最后1分钟：强制卖出持仓的 75%，锁定资金
  T-0        结算：剩余 25% 由市场决定
─────────────────────────────────────────────
每笔最大 $10
"""
import time
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON
from indicators import get_signals

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

TRADE_AMOUNT = min(float(os.getenv('TRADE_AMOUNT_USD', 5.0)), 10.0)
PARTIAL_SELL_RATIO = 0.75   # T-60 时卖出 75%
ENTRY_PRICE_MIN = 0.48
ENTRY_PRICE_MAX = 0.72

# 持仓状态
position = None  # dict or None
partial_sold = False

stats = {'wins': 0, 'losses': 0, 'total_pnl': 0.0, 'trades': 0}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def send_tg(msg):
    try:
        TOKEN = os.getenv('TELEGRAM_TOKEN')
        CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
        requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                      json={'chat_id': CHAT_ID, 'text': msg}, timeout=5)
    except:
        pass

def get_current_market(coin='btc'):
    now = int(time.time())
    window_start = (now // 300) * 300
    window_end = window_start + 300
    slug = f'{coin}-updown-5m-{window_start}'
    try:
        r = requests.get(f'{GAMMA_API}/events?slug={slug}', timeout=5)
        events = r.json()
        if events:
            mkt = events[0]['markets'][0]
            token_ids = json.loads(mkt['clobTokenIds'])
            prices = json.loads(mkt['outcomePrices'])
            return {
                'question': mkt['question'],
                'up_token': token_ids[0],
                'down_token': token_ids[1],
                'up_price': float(prices[0]),
                'down_price': float(prices[1]),
                'window_end': window_end,
                'window_start': window_start,
            }
    except Exception as e:
        log(f"市场查询失败: {e}")
    return None

def get_best_ask(token_id):
    try:
        book = client.get_order_book(token_id)
        if book and book.asks:
            return float(book.asks[0].price), float(book.asks[0].size)
    except:
        pass
    return None, None

def get_best_bid(token_id):
    try:
        book = client.get_order_book(token_id)
        if book and book.bids:
            return float(book.bids[0].price), float(book.bids[0].size)
    except:
        pass
    return None, None

def place_order(token_id, price, size, side='BUY'):
    try:
        order_args = OrderArgs(token_id=token_id, price=price, size=size, side=side)
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.FOK)
        return resp
    except Exception as e:
        log(f"下单异常: {e}")
        return None

def partial_close():
    """T-60：卖出持仓的 75%"""
    global position, partial_sold
    if not position or partial_sold:
        return

    sell_size = round(position['size'] * PARTIAL_SELL_RATIO, 2)
    if sell_size < 1.0:
        log("⚠️ 卖出数量过小，跳过部分平仓")
        partial_sold = True
        return

    bid, _ = get_best_bid(position['token_id'])
    if not bid:
        log("⚠️ 无买单，无法部分平仓")
        partial_sold = True
        return

    log(f"⏰ T-60 部分平仓：卖出 {sell_size} tokens @ ${bid:.4f} (75%)")
    resp = place_order(position['token_id'], bid, sell_size, side='SELL')

    if resp:
        sell_value = bid * sell_size
        buy_value = position['buy_price'] * sell_size
        pnl_partial = sell_value - buy_value
        stats['total_pnl'] += pnl_partial
        position['size'] -= sell_size  # 剩余 25%

        msg = f"""💸 【龙虾火控 - T-60 部分平仓】
━━━━━━━━━━━━━━━━━━━━━
卖出 75%: {sell_size} tokens @ ${bid:.4f}
买入均价: ${position['buy_price']:.4f}
本次盈亏: ${pnl_partial:+.4f}
剩余 25%: {position['size']:.2f} tokens (持有至结算)
━━━━━━━━━━━━━━━━━━━━━"""
        log(msg)
        send_tg(msg)
        partial_sold = True
    else:
        log("❌ 部分平仓失败")

def entry(market, direction, ask_price, size):
    """入场下单"""
    global position, partial_sold
    token_id = market['up_token'] if direction == 'UP' else market['down_token']
    log(f"🎯 入场: {direction} | ${ask_price:.4f} × {size} tokens = ${ask_price*size:.2f}")
    resp = place_order(token_id, ask_price, size, side='BUY')

    if resp and resp.get('status') == 'matched':
        position = {
            'token_id': token_id,
            'size': size,
            'buy_price': ask_price,
            'direction': direction,
            'window_end': market['window_end'],
        }
        partial_sold = False
        stats['trades'] += 1

        msg = f"""🎯 【龙虾火控 - 提前布局入场】
━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%H:%M:%S')}
📊 {market['question']}
🎲 方向: {direction}
💵 买入: ${ask_price*size:.2f} @ ${ask_price:.4f}
📦 数量: {size} tokens
📋 策略: T-60 卖出75% + 25%持有至结算
━━━━━━━━━━━━━━━━━━━━━"""
        log(msg)
        send_tg(msg)
        return True
    else:
        log(f"❌ 入场失败: {resp}")
        return False

def run():
    global position, partial_sold
    log(f"🚀 提前布局策略 v2 启动 (每笔 ${TRADE_AMOUNT:.2f}，最大 $10)")
    send_tg(f"""🚀 【龙虾火控 - 策略 v2 启动】
━━━━━━━━━━━━━━━━━━━━━
策略: 提前布局 (第2~4分钟入场)
平仓: T-60 卖出75% + 25%持有结算
金额: ${TRADE_AMOUNT:.2f}/笔 (最大$10)
━━━━━━━━━━━━━━━━━━━━━""")

    while True:
        try:
            now = int(time.time())
            window_start = (now // 300) * 300
            window_end = window_start + 300
            elapsed = now - window_start
            remaining = window_end - now

            # ── 新窗口重置 ──────────────────────────────────
            if position and position['window_end'] != window_end:
                # 上一个窗口的剩余 25% 已结算，记录
                log(f"📊 窗口结束，剩余 25% ({position['size']:.2f} tokens) 已结算")
                position = None
                partial_sold = False

            # ── T-60：部分平仓（75%）─────────────────────────
            if position and not partial_sold and remaining <= 60:
                partial_close()

            # ── T+120~T+240：入场决策（第2~4分钟）──────────
            if not position and 120 <= elapsed <= 240:
                log(f"🔍 扫描入场 (已过 {elapsed}s / 剩余 {remaining}s)...")

                sig, rsi, mom = get_signals('BTCUSDT')
                log(f"   BTC 信号: {sig} | RSI: {rsi:.2f} | 动量: {mom:+.3f}%")

                if sig in ['UP', 'DOWN']:
                    market = get_current_market('btc')
                    if market:
                        token_id = market['up_token'] if sig == 'UP' else market['down_token']
                        ask, ask_size = get_best_ask(token_id)

                        if ask and ENTRY_PRICE_MIN <= ask <= ENTRY_PRICE_MAX:
                            size = round(TRADE_AMOUNT / ask, 2)
                            entry(market, sig, ask, size)
                        elif ask:
                            log(f"   价格 ${ask:.4f} 不在 ${ENTRY_PRICE_MIN}~${ENTRY_PRICE_MAX} 区间，跳过")
                        else:
                            log("   无卖单，跳过")
                else:
                    log(f"   信号中性，等待下一次扫描")

            time.sleep(5)

        except KeyboardInterrupt:
            log("⛔ 手动停止")
            break
        except Exception as e:
            log(f"循环错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__ == '__main__':
    run()
