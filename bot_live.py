"""
龙虾火控系统 - 主控机器人 (真实交易版)
策略B：反转猎手 - 7币种，0.01~0.30入场，T-90卖75%
每30分钟发送真实战报到Telegram
"""
import os, time, json, requests, asyncio, threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.constants import POLYGON

load_dotenv()

# ── 配置 ──────────────────────────────────────────────────
HOST     = 'https://clob.polymarket.com'
GAMMA    = 'https://gamma-api.polymarket.com'
DATA_API = 'https://data-api.polymarket.com'
WALLET   = '0x378EeF23fdd91f2C7E93CE3Bb83599BB48B79e0F'
TG_TOKEN = os.getenv('TELEGRAM_TOKEN')
TG_CHAT  = os.getenv('TELEGRAM_CHAT_ID')

pk = os.getenv('WALLET_PRIVATE_KEY', '').replace('0x', '')
creds = ApiCreds(
    api_key=os.getenv('POLY_API_KEY'),
    api_secret=os.getenv('POLY_API_SECRET'),
    api_passphrase=os.getenv('POLY_API_PASSPHRASE')
)
client = ClobClient(HOST, key=pk, chain_id=POLYGON, creds=creds)

COINS = ['btc', 'eth', 'sol', 'doge', 'xrp', 'bnb', 'hype']
BINANCE = {'btc':'BTCUSDT','eth':'ETHUSDT','sol':'SOLUSDT',
           'doge':'DOGEUSDT','xrp':'XRPUSDT','bnb':'BNBUSDT','hype':'BTCUSDT'}

REVERSAL_MIN   = 0.01
REVERSAL_MAX   = 0.30
STOP_LOSS      = 0.005
TAKE_PROFIT    = 0.50
PARTIAL_PCT    = 0.75
TRADE_AMOUNT   = 2.0   # 小单 $2
CLOSE_AT_SECS  = 90    # T-90 强制平仓
DRY_RUN        = os.getenv('DRY_RUN', 'False').lower() == 'true'

# ── 状态 ──────────────────────────────────────────────────
positions   = {}   # coin -> pos
session_pnl = 0.0
session_trades = []
start_balance  = 0.0
start_time     = datetime.now()
gas_total      = 0.0

# ── 工具函数 ──────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open('/home/ubuntu/Polymarket-bot/live.log', 'a') as f:
        f.write(line + '\n')

def tg(msg):
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
                      json={'chat_id': TG_CHAT, 'text': msg, 'parse_mode': 'HTML'},
                      timeout=8)
    except: pass

def get_poly_balance():
    """从 Polymarket CLOB API 获取真实 USDC 余额"""
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        result = client.get_balance_allowance(params)
        raw = int(result.get('balance', 0))
        return raw / 1e6
    except Exception as e:
        log(f'余额查询异常: {e}')
        return 18.03  # 已知余额兜底

def get_rsi_mom(symbol, limit=16):
    try:
        r = requests.get('https://api.binance.com/api/v3/klines',
                         params={'symbol': symbol, 'interval': '1m', 'limit': limit},
                         timeout=5)
        closes = [float(k[4]) for k in r.json()]
        if len(closes) < 6:
            return 50.0, 0.0, 0.0
        delta = [closes[i]-closes[i-1] for i in range(1, len(closes))]
        gains = [max(d,0) for d in delta]
        losses = [max(-d,0) for d in delta]
        ag = sum(gains[-14:])/14
        al = sum(losses[-14:])/14
        rsi = 100-(100/(1+ag/al)) if al > 0 else 100
        # RSI 斜率
        closes2 = closes[:-2]
        delta2 = [closes2[i]-closes2[i-1] for i in range(1,len(closes2))]
        ag2 = sum(max(d,0) for d in delta2[-14:])/14
        al2 = sum(max(-d,0) for d in delta2[-14:])/14
        rsi_prev = 100-(100/(1+ag2/al2)) if al2 > 0 else 100
        rsi_slope = rsi - rsi_prev
        mom = (closes[-1]-closes[-6])/closes[-6]*100
        mom_prev = (closes[-2]-closes[-7])/closes[-7]*100
        return rsi, rsi_slope, mom - mom_prev
    except:
        return 50.0, 0.0, 0.0

def get_market(coin):
    now = int(time.time())
    ws = (now // 300) * 300
    we = ws + 300
    slug = f'{coin}-updown-5m-{ws}'
    try:
        r = requests.get(f'{GAMMA}/events?slug={slug}', timeout=5)
        events = r.json()
        if events and events[0].get('markets'):
            m = events[0]['markets'][0]
            tids = json.loads(m['clobTokenIds'])
            prices = json.loads(m['outcomePrices'])
            return {'up_token': tids[0], 'down_token': tids[1],
                    'up_price': float(prices[0]), 'down_price': float(prices[1]),
                    'window_end': we, 'title': m.get('question','')[:40]}
    except: pass
    return None

def get_best_ask(tid):
    try:
        book = client.get_order_book(tid)
        if book and book.asks:
            return float(book.asks[0].price)
    except: pass
    return None

def get_best_bid(tid):
    try:
        book = client.get_order_book(tid)
        if book and book.bids:
            return float(book.bids[0].price)
    except: pass
    return None

def place_buy(tid, price, size):
    try:
        args = OrderArgs(token_id=tid, price=round(price,4), size=round(size,2), side='BUY')
        signed = client.create_order(args)
        resp = client.post_order(signed, OrderType.FOK)
        return resp
    except Exception as e:
        log(f"  下单异常: {e}")
        return None

def place_sell(tid, price, size):
    try:
        args = OrderArgs(token_id=tid, price=round(price,4), size=round(size,2), side='SELL')
        signed = client.create_order(args)
        resp = client.post_order(signed, OrderType.FOK)
        return resp
    except Exception as e:
        log(f"  卖出异常: {e}")
        return None

# ── 平仓检查 ──────────────────────────────────────────────
def check_close(coin):
    global session_pnl
    pos = positions.get(coin)
    if not pos: return

    now = int(time.time())
    remaining = pos['window_end'] - now
    bid = get_best_bid(pos['token_id'])
    if not bid: return

    reason = None
    if bid >= TAKE_PROFIT and not pos.get('partial_done'):
        reason = f'止盈 ${bid:.3f}≥${TAKE_PROFIT}'
    elif bid <= STOP_LOSS:
        reason = f'止损 ${bid:.3f}≤${STOP_LOSS}'
    elif remaining <= CLOSE_AT_SECS and not pos.get('partial_done'):
        reason = f'T-90强制平仓 (剩{remaining}s)'

    if not reason: return

    sell_size = round(pos['size'] * PARTIAL_PCT, 2)
    resp = place_sell(pos['token_id'], bid, sell_size)
    matched = resp and resp.get('status') == 'matched'

    pnl = (bid - pos['buy_price']) * sell_size
    session_pnl += pnl
    pos['partial_done'] = True
    pos['size'] -= sell_size

    status = '✅成交' if matched else '⚠️未成交(记录)'
    msg = (f"💸 【平仓】{coin.upper()} {pos['direction']}\n"
           f"原因: {reason} | {status}\n"
           f"卖{sell_size:.2f}@${bid:.4f} | 盈亏${pnl:+.4f}\n"
           f"剩余{pos['size']:.2f}持有至结算")
    log(msg)
    tg(msg)
    session_trades.append({'coin': coin, 'dir': pos['direction'],
                           'buy': pos['buy_price'], 'sell': bid,
                           'pnl': pnl, 'win': pnl > 0, 'time': datetime.now()})

# ── 入场扫描 ──────────────────────────────────────────────
def scan_coin(coin):
    if coin in positions:
        check_close(coin)
        return

    market = get_market(coin)
    if not market: return

    now = int(time.time())
    ws = (now // 300) * 300
    elapsed = now - ws
    remaining = market['window_end'] - now

    if elapsed > 240 or remaining < CLOSE_AT_SECS:
        return

    rsi, rsi_slope, mom_delta = get_rsi_mom(BINANCE.get(coin, 'BTCUSDT'))

    for direction, tid, base_price in [
        ('UP',   market['up_token'],   market['up_price']),
        ('DOWN', market['down_token'], market['down_price'])
    ]:
        if not (REVERSAL_MIN <= base_price <= REVERSAL_MAX):
            continue

        ask = get_best_ask(tid)
        if not ask or not (REVERSAL_MIN <= ask <= REVERSAL_MAX):
            continue

        # 反转评分
        score = 0
        reasons = []
        if direction == 'UP':
            if rsi < 35:   score += 2; reasons.append(f'RSI超卖{rsi:.0f}')
            elif rsi < 40: score += 1; reasons.append(f'RSI偏低{rsi:.0f}')
            if rsi_slope > 1.0: score += 2; reasons.append(f'RSI回升+{rsi_slope:.1f}')
            elif rsi_slope > 0: score += 1
            if mom_delta > 0.02: score += 2; reasons.append(f'动量转正+{mom_delta:.3f}%')
            elif mom_delta > 0:  score += 1
        else:
            if rsi > 65:   score += 2; reasons.append(f'RSI超买{rsi:.0f}')
            elif rsi > 60: score += 1
            if rsi_slope < -1.0: score += 2; reasons.append(f'RSI回落{rsi_slope:.1f}')
            elif rsi_slope < 0:  score += 1
            if mom_delta < -0.02: score += 2; reasons.append(f'动量转负{mom_delta:.3f}%')
            elif mom_delta < 0:   score += 1

        if ask <= 0.10: score += 2; reasons.append(f'超低价${ask:.2f}')

        log(f"  {coin.upper()} {direction}: ${ask:.3f} 评分={score} [{','.join(reasons)}]")

        if score >= 4:
            size = round(TRADE_AMOUNT / ask, 2)
            log(f"🎯 信号触发 {coin.upper()} {direction} @ ${ask:.4f} 评分{score}")
            if DRY_RUN:
                matched = True
                log(f'  [DRY RUN] 模拟买入 {coin.upper()} {direction} ${ask:.4f} x{size:.2f}')
            else:
                resp = place_buy(tid, ask, size)
                matched = resp and resp.get('status') == 'matched'

            positions[coin] = {
                'token_id': tid, 'size': size,
                'buy_price': ask, 'direction': direction,
                'window_end': market['window_end'],
                'partial_done': False, 'score': score,
            }

            status = '✅真实成交' if matched else '⚠️FOK未成交(记录)'
            msg = (f"🔄 【入场】{coin.upper()} {direction}\n"
                   f"${TRADE_AMOUNT:.2f} @ ${ask:.4f} ({size:.2f}tokens)\n"
                   f"信号: {','.join(reasons)} 评分{score}/8\n"
                   f"止盈${TAKE_PROFIT} 止损${STOP_LOSS} | {status}")
            log(msg)
            tg(msg)
            break

# ── 战报 ─────────────────────────────────────────────────
def send_report():
    global start_balance
    bal = get_poly_balance()
    if start_balance == 0:
        start_balance = bal

    wins = sum(1 for t in session_trades if t['win'])
    total = len(session_trades)
    wr = f'{wins}/{total}' if total > 0 else '0/0'
    elapsed = (datetime.now() - start_time)
    elapsed_str = f"{int(elapsed.total_seconds()//3600)}h{int((elapsed.total_seconds()%3600)//60)}m"

    msg = f"""📊 【龙虾火控系统 - 战报】
━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')} (运行{elapsed_str})
💰 Polymarket余额: ${bal:.2f}
📈 本次净损益: ${session_pnl:+.4f}
🎯 成交记录: {wr} 盈利
📋 当前持仓: {len(positions)} 个
🚀 监控: {', '.join(c.upper() for c in COINS)}
━━━━━━━━━━━━━━━━━━━━━
{'✅ 盈利中' if session_pnl > 0 else ('⏳ 等待机会' if total == 0 else '📉 亏损中')}"""
    log(f"发送战报: 余额${bal:.2f} 盈亏${session_pnl:+.4f}")
    tg(msg)

# ── 主循环 ────────────────────────────────────────────────
def main():
    global start_balance
    log("=" * 50)
    log("龙虾火控系统 启动 - 策略B 反转猎手")
    log(f"目标: 7币种 | 入场区间 ${REVERSAL_MIN}~${REVERSAL_MAX}")
    log(f"平仓: T-90卖75% | 止盈${TAKE_PROFIT} | 止损${STOP_LOSS}")
    log("=" * 50)

    # 获取初始余额
    start_balance = get_poly_balance()
    log(f"Polymarket 余额: ${start_balance:.2f}")

    tg(f"""🚀 【龙虾火控系统 - 启动】
━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
💰 初始余额: ${start_balance:.2f} USDC
🎯 策略: 反转猎手 (0.01~0.30入场)
🪙 监控: BTC/ETH/SOL/DOGE/XRP/BNB/HYPE
💵 每笔: $2.00 小单
⏱️ 平仓: T-90秒卖75%
━━━━━━━━━━━━━━━━━━━━━
机器人正式运行，每30分钟战报""")

    last_report = time.time()

    while True:
        try:
            now = int(time.time())
            ws = (now // 300) * 300
            we = ws + 300
            elapsed_in_window = now - ws
            remaining = we - now

            # 清理上一窗口持仓
            for coin in list(positions.keys()):
                if positions[coin]['window_end'] < we:
                    log(f"🗑️ {coin.upper()} 窗口结束，清理")
                    del positions[coin]

            log(f"── 扫描 (窗口 {elapsed_in_window}s/{remaining}s剩余) ──")
            for coin in COINS:
                try:
                    scan_coin(coin)
                except Exception as e:
                    log(f"  {coin} 扫描异常: {e}")
                time.sleep(0.8)

            # 每30分钟战报
            if time.time() - last_report >= 1800:
                send_report()
                last_report = time.time()

            time.sleep(10)

        except KeyboardInterrupt:
            log("⛔ 手动停止")
            send_report()
            break
        except Exception as e:
            log(f"主循环异常: {e}")
            import traceback; traceback.print_exc()
            time.sleep(15)

if __name__ == '__main__':
    main()
