"""
策略B：反转猎手 (Reversal Hunter)
─────────────────────────────────────────────
逻辑：
  7个币种同时监控 YES/NO token
  当某个 token 价格跌至 0.20~0.30 区间时：
    → 说明市场认为该方向概率仅 20~30%
    → 但如果 Binance 实时价格显示动量开始反转
    → 则存在"概率修正"机会：token 从 0.25 → 0.50+ 有 2x 空间
  
  反转信号判断：
    1. RSI < 35 且开始回升（RSI 斜率 > 0）→ 超卖反转
    2. 动量从负转正（最近2根K线动量差 > 0）
    3. 价格在 0.20~0.30 区间（赔率 > 3:1）
  
  平仓规则：
    - 价格涨到 0.50+ 时，卖出 75%
    - 价格跌破 0.15 止损（止损线）
    - T-60 强制卖出 75%
─────────────────────────────────────────────
"""
import time
import os
import json
import asyncio
import requests
from datetime import datetime
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

TRADE_AMOUNT = min(float(os.getenv('TRADE_AMOUNT_USD', 5.0)), 10.0)
REVERSAL_MIN = 0.20
REVERSAL_MAX = 0.30
STOP_LOSS    = 0.15
TAKE_PROFIT  = 0.50
PARTIAL_SELL = 0.75

COINS = ['btc', 'eth', 'sol', 'doge', 'xrp', 'bnb', 'hype']
BINANCE_SYMBOLS = {
    'btc': 'BTCUSDT', 'eth': 'ETHUSDT', 'sol': 'SOLUSDT',
    'doge': 'DOGEUSDT', 'xrp': 'XRPUSDT', 'bnb': 'BNBUSDT',
    'hype': 'BTCUSDT'  # HYPE 无 Binance 数据，用 BTC 替代
}

positions = {}  # coin -> position dict

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def send_tg(msg):
    try:
        TOKEN = os.getenv('TELEGRAM_TOKEN')
        CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
        requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                      json={'chat_id': CHAT_ID, 'text': msg}, timeout=5)
    except:
        pass

def get_binance_rsi_mom(symbol, limit=16):
    """获取 RSI 和动量"""
    try:
        r = requests.get(
            'https://api.binance.com/api/v3/klines',
            params={'symbol': symbol, 'interval': '1m', 'limit': limit},
            timeout=5
        )
        closes = [float(k[4]) for k in r.json()]
        if len(closes) < 6:
            return 50.0, 0.0, 0.0

        # RSI
        import numpy as np
        delta = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in delta]
        losses = [max(-d, 0) for d in delta]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

        # RSI 斜率（最近3根K线的RSI变化）
        def quick_rsi(cls):
            d = [cls[i]-cls[i-1] for i in range(1,len(cls))]
            g = sum(max(x,0) for x in d[-14:]) / 14
            l = sum(max(-x,0) for x in d[-14:]) / 14
            return 100-(100/(1+g/l)) if l>0 else 100

        rsi_prev = quick_rsi(closes[:-2])
        rsi_slope = rsi - rsi_prev

        # 动量
        mom = (closes[-1] - closes[-6]) / closes[-6] * 100
        mom_prev = (closes[-2] - closes[-7]) / closes[-7] * 100
        mom_delta = mom - mom_prev

        return rsi, rsi_slope, mom_delta
    except Exception as e:
        return 50.0, 0.0, 0.0

def get_market(coin):
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
                'coin': coin,
                'question': mkt['question'],
                'up_token': token_ids[0],
                'down_token': token_ids[1],
                'up_price': float(prices[0]),
                'down_price': float(prices[1]),
                'window_end': window_end,
            }
    except:
        pass
    return None

def get_best_ask(token_id):
    try:
        book = client.get_order_book(token_id)
        if book and book.asks:
            return float(book.asks[0].price)
    except:
        pass
    return None

def get_best_bid(token_id):
    try:
        book = client.get_order_book(token_id)
        if book and book.bids:
            return float(book.bids[0].price)
    except:
        pass
    return None

def place_order(token_id, price, size, side='BUY'):
    try:
        order_args = OrderArgs(token_id=token_id, price=price, size=size, side=side)
        signed = client.create_order(order_args)
        resp = client.post_order(signed, OrderType.FOK)
        return resp
    except Exception as e:
        log(f"下单异常: {e}")
        return None

def check_and_close(coin):
    """检查止盈/止损/T-60平仓"""
    pos = positions.get(coin)
    if not pos:
        return

    now = int(time.time())
    remaining = pos['window_end'] - now
    bid = get_best_bid(pos['token_id'])
    if not bid:
        return

    reason = None
    if bid >= TAKE_PROFIT and not pos.get('partial_sold'):
        reason = f"🎯 止盈 (${bid:.4f} ≥ ${TAKE_PROFIT})"
    elif bid <= STOP_LOSS:
        reason = f"🛑 止损 (${bid:.4f} ≤ ${STOP_LOSS})"
    elif remaining <= 60 and not pos.get('partial_sold'):
        reason = f"⏰ T-60 强制平仓"

    if reason:
        sell_size = round(pos['size'] * PARTIAL_SELL, 2)
        resp = place_order(pos['token_id'], bid, sell_size, side='SELL')
        pnl = (bid - pos['buy_price']) * sell_size
        pos['size'] -= sell_size
        pos['partial_sold'] = True

        msg = f"""💸 【反转猎手 - 平仓】
━━━━━━━━━━━━━━━━━━━━━
币种: {coin.upper()}  方向: {pos['direction']}
原因: {reason}
卖出: {sell_size} tokens @ ${bid:.4f}
盈亏: ${pnl:+.4f}
剩余: {pos['size']:.2f} tokens (持有至结算)
━━━━━━━━━━━━━━━━━━━━━"""
        log(msg)
        send_tg(msg)

def scan_coin(coin):
    """扫描单个币种的反转机会"""
    if coin in positions:
        check_and_close(coin)
        return

    market = get_market(coin)
    if not market:
        return

    now = int(time.time())
    window_start = (now // 300) * 300
    elapsed = now - window_start
    remaining = market['window_end'] - now

    # 只在前4分钟内入场
    if elapsed > 240 or remaining < 60:
        return

    symbol = BINANCE_SYMBOLS.get(coin, 'BTCUSDT')
    rsi, rsi_slope, mom_delta = get_binance_rsi_mom(symbol)

    # 检查 UP token 是否在反转区间
    for direction, token_id, price in [
        ('UP', market['up_token'], market['up_price']),
        ('DOWN', market['down_token'], market['down_price'])
    ]:
        if not (REVERSAL_MIN <= price <= REVERSAL_MAX):
            continue

        ask = get_best_ask(token_id)
        if not ask or not (REVERSAL_MIN <= ask <= REVERSAL_MAX):
            continue

        # 反转信号：RSI 超卖 + 开始回升 + 动量转正
        reversal_score = 0
        reasons = []

        if rsi < 35:
            reversal_score += 2
            reasons.append(f"RSI超卖({rsi:.1f})")
        elif rsi < 40:
            reversal_score += 1
            reasons.append(f"RSI偏低({rsi:.1f})")

        if rsi_slope > 1.0:
            reversal_score += 2
            reasons.append(f"RSI回升(+{rsi_slope:.1f})")
        elif rsi_slope > 0:
            reversal_score += 1

        if mom_delta > 0.02:
            reversal_score += 2
            reasons.append(f"动量转正(+{mom_delta:.3f}%)")
        elif mom_delta > 0:
            reversal_score += 1

        # 价格越低，赔率越高，加分
        if ask <= 0.23:
            reversal_score += 1
            reasons.append(f"超低价(${ask:.2f})")

        log(f"  {coin.upper()} {direction}: 价格=${ask:.2f} 反转分={reversal_score} [{', '.join(reasons)}]")

        if reversal_score >= 4:
            size = round(TRADE_AMOUNT / ask, 2)
            log(f"🎯 反转信号触发！{coin.upper()} {direction} @ ${ask:.4f}")
            resp = place_order(token_id, ask, size, side='BUY')

            if resp and resp.get('status') == 'matched':
                positions[coin] = {
                    'token_id': token_id,
                    'size': size,
                    'buy_price': ask,
                    'direction': direction,
                    'window_end': market['window_end'],
                    'partial_sold': False,
                    'reversal_score': reversal_score,
                }
                msg = f"""🔄 【反转猎手 - 入场】
━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%H:%M:%S')}
🪙 {coin.upper()} | {direction}
💵 买入: ${TRADE_AMOUNT:.2f} @ ${ask:.4f}
📦 数量: {size:.2f} tokens
🎯 反转信号: {', '.join(reasons)}
📊 反转评分: {reversal_score}/7
🎯 止盈: ${TAKE_PROFIT}  止损: ${STOP_LOSS}
━━━━━━━━━━━━━━━━━━━━━"""
                log(msg)
                send_tg(msg)
                break

def run():
    log(f"🔄 反转猎手策略启动 (7币种并发，每笔 ${TRADE_AMOUNT:.2f})")
    send_tg(f"""🔄 【反转猎手策略启动】
━━━━━━━━━━━━━━━━━━━━━
监控: {', '.join(c.upper() for c in COINS)}
入场条件: Token 价格 20~30 美分 + 反转信号
止盈: ${TAKE_PROFIT}  止损: ${STOP_LOSS}
平仓: T-60 卖出75% + 25%持有结算
金额: ${TRADE_AMOUNT:.2f}/笔
━━━━━━━━━━━━━━━━━━━━━""")

    while True:
        try:
            now = int(time.time())
            window_start = (now // 300) * 300
            window_end = window_start + 300

            # 清理上一个窗口的持仓
            for coin in list(positions.keys()):
                if positions[coin]['window_end'] < window_end:
                    log(f"📊 {coin.upper()} 窗口结束，清理持仓")
                    del positions[coin]

            log(f"── 扫描 7 币种 (窗口剩余 {window_end - now}s) ──")
            for coin in COINS:
                scan_coin(coin)
                time.sleep(0.5)  # 避免 API 限速

            time.sleep(10)

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
