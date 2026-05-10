"""
龙虾火控系统 - 做市商策略 (Market Maker)
在 Polymarket 5分钟市场提供流动性，赚取价差
"""
import os, time, json, requests
from datetime import datetime
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

SPREAD         = 0.06  # 目标价差 6%
TRADE_AMOUNT   = 5.0   # 每侧挂单 $5
CANCEL_AT_SECS = 60    # T-60 撤销所有未成交挂单
DRY_RUN        = os.getenv('DRY_RUN', 'False').lower() == 'true'

# ── 状态 ──────────────────────────────────────────────────
active_orders = {}  # order_id -> details
session_pnl = 0.0
start_balance = 0.0

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open('/home/ubuntu/Polymarket-bot/mm.log', 'a') as f:
        f.write(line + '\n')

def tg(msg):
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
                      json={'chat_id': TG_CHAT, 'text': msg, 'parse_mode': 'HTML'},
                      timeout=8)
    except: pass

def get_poly_balance():
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        result = client.get_balance_allowance(params)
        return int(result.get('balance', 0)) / 1e6
    except:
        return 18.03

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

def place_limit_order(tid, price, size, side):
    if DRY_RUN:
        log(f"  [DRY RUN] 模拟挂单 {side} @ ${price:.3f} x{size:.2f}")
        return {'orderID': f'dry_{time.time()}'}
    try:
        args = OrderArgs(token_id=tid, price=round(price,3), size=round(size,2), side=side)
        signed = client.create_order(args)
        resp = client.post_order(signed, OrderType.GTC)
        return resp
    except Exception as e:
        log(f"  挂单异常: {e}")
        return None

def cancel_order(order_id):
    if DRY_RUN or order_id.startswith('dry_'):
        log(f"  [DRY RUN] 模拟撤单 {order_id}")
        return True
    try:
        client.cancel_order(order_id)
        return True
    except Exception as e:
        log(f"  撤单异常: {e}")
        return False

def make_market(coin):
    market = get_market(coin)
    if not market: return

    now = int(time.time())
    remaining = market['window_end'] - now

    # T-60 撤单
    if remaining <= CANCEL_AT_SECS:
        to_cancel = [oid for oid, details in active_orders.items() if details['coin'] == coin]
        for oid in to_cancel:
            log(f"⏳ T-{remaining}s 撤销 {coin.upper()} 挂单")
            cancel_order(oid)
            del active_orders[oid]
        return

    # 如果已经有挂单，跳过
    if any(d['coin'] == coin for d in active_orders.values()):
        return

    # 只有在窗口前 3 分钟挂单
    if remaining < 180:
        return

    # 计算挂单价格
    mid_price = market['up_price']
    if not (0.30 <= mid_price <= 0.70):
        return  # 价格太偏，不做市

    bid_price = max(0.01, mid_price - SPREAD/2)
    ask_price = min(0.99, mid_price + SPREAD/2)
    
    size = round(TRADE_AMOUNT / mid_price, 2)

    log(f"📈 {coin.upper()} 做市: Bid ${bid_price:.3f} | Ask ${ask_price:.3f}")
    
    # 挂买单 (Bid)
    resp_bid = place_limit_order(market['up_token'], bid_price, size, 'BUY')
    if resp_bid and resp_bid.get('orderID'):
        active_orders[resp_bid['orderID']] = {'coin': coin, 'side': 'BUY', 'price': bid_price, 'size': size}
        
    # 挂卖单 (Ask)
    resp_ask = place_limit_order(market['up_token'], ask_price, size, 'SELL')
    if resp_ask and resp_ask.get('orderID'):
        active_orders[resp_ask['orderID']] = {'coin': coin, 'side': 'SELL', 'price': ask_price, 'size': size}

def main():
    global start_balance
    log("=" * 50)
    log("龙虾火控系统 启动 - 做市商策略")
    log(f"目标: 7币种 | 目标价差 {SPREAD*100}%")
    log(f"撤单: T-{CANCEL_AT_SECS}s | DRY_RUN: {DRY_RUN}")
    log("=" * 50)

    start_balance = get_poly_balance()
    log(f"Polymarket 余额: ${start_balance:.2f}")

    tg(f"""🚀 【龙虾火控系统 - 做市商启动】
━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
💰 初始余额: ${start_balance:.2f} USDC
🎯 策略: 流动性提供 (价差 {SPREAD*100}%)
🪙 监控: BTC/ETH/SOL/DOGE/XRP/BNB/HYPE
💵 每侧挂单: ${TRADE_AMOUNT:.2f}
⏱️ 撤单: T-{CANCEL_AT_SECS}秒
━━━━━━━━━━━━━━━━━━━━━""")

    while True:
        try:
            for coin in COINS:
                make_market(coin)
                time.sleep(0.5)
            time.sleep(5)
        except KeyboardInterrupt:
            log("⛔ 手动停止")
            break
        except Exception as e:
            log(f"主循环异常: {e}")
            time.sleep(15)

if __name__ == '__main__':
    main()
