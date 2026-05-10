"""
提前布局策略 (Early Bird Strategy)
1. 窗口开始后 60~120 秒内，用 RSI + 动量预判方向
2. 如果目标 token 价格在 $0.50 ~ $0.70 之间，买入 (最大 $10)
3. 窗口结束前 30 秒 (T-30)，强制平仓锁利或止损
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

TRADE_AMOUNT = float(os.getenv('TRADE_AMOUNT_USD', 5.0))
if TRADE_AMOUNT > 10.0:
    TRADE_AMOUNT = 10.0

# 状态记录
current_position = None  # {'token_id': '...', 'size': 10.5, 'buy_price': 0.55, 'window_end': 1234567890}

def send_tg(msg):
    try:
        TOKEN = os.getenv('TELEGRAM_TOKEN')
        CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
        requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                      json={'chat_id': CHAT_ID, 'text': msg}, timeout=5)
    except:
        pass

def get_current_market():
    now = int(time.time())
    window_start = (now // 300) * 300
    window_end = window_start + 300
    event_slug = f'btc-updown-5m-{window_start}'
    
    try:
        r = requests.get(f'{GAMMA_API}/events?slug={event_slug}', timeout=5)
        events = r.json()
        if events:
            market = events[0]['markets'][0]
            token_ids = json.loads(market['clobTokenIds'])
            return {
                'up_token': token_ids[0],
                'down_token': token_ids[1],
                'window_end': window_end
            }
    except:
        pass
    return None

def close_position():
    global current_position
    if not current_position:
        return
        
    print(f"\n[T-30 平仓] 准备平仓...")
    try:
        # 获取最优买价 (Bid) 来卖出
        book = client.get_order_book(current_position['token_id'])
        bids = book.bids if book and book.bids else []
        if not bids:
            print("⚠️ 无买单，无法平仓")
            return
            
        best_bid = float(bids[0].price)
        size = current_position['size']
        
        order_args = OrderArgs(
            token_id=current_position['token_id'],
            price=best_bid,
            size=size,
            side='SELL',
        )
        signed_order = client.create_order(order_args)
        resp = client.post_order(signed_order, OrderType.FOK)
        
        sell_value = best_bid * size
        buy_value = current_position['buy_price'] * size
        pnl = sell_value - buy_value
        
        msg = f"""💸 【龙虾火控 - 平仓战报】
━━━━━━━━━━━━━━━━━━━━━
卖出价格: ${best_bid:.4f}
买入价格: ${current_position['buy_price']:.4f}
净利润: ${pnl:+.4f}
状态: {resp.get('status', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━"""
        print(msg)
        send_tg(msg)
        current_position = None
        
    except Exception as e:
        print(f"平仓失败: {e}")

def run_loop():
    global current_position
    print(f"🚀 提前布局策略启动 (每笔 ${TRADE_AMOUNT:.2f})")
    send_tg(f"🚀 提前布局策略启动\n模式: 真实交易\n金额: ${TRADE_AMOUNT:.2f}/笔")
    
    while True:
        try:
            now = int(time.time())
            window_start = (now // 300) * 300
            window_end = window_start + 300
            elapsed = now - window_start
            remaining = window_end - now
            
            # 1. 平仓逻辑 (T-30)
            if current_position and remaining <= 30:
                close_position()
                time.sleep(35) # 等待下一个窗口
                continue
                
            # 2. 入场逻辑 (T+60 到 T+120)
            if not current_position and 60 <= elapsed <= 120:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 扫描入场机会 (已过 {elapsed}s)...")
                
                sig, rsi, mom = get_signals('BTCUSDT')
                print(f"指标 -> 信号: {sig} | RSI: {rsi:.2f} | 动量: {mom:+.3f}%")
                
                if sig in ['UP', 'DOWN']:
                    market = get_current_market()
                    if not market:
                        time.sleep(5)
                        continue
                        
                    target_token = market['up_token'] if sig == 'UP' else market['down_token']
                    
                    # 检查价格
                    book = client.get_order_book(target_token)
                    asks = book.asks if book and book.asks else []
                    if asks:
                        best_ask = float(asks[0].price)
                        print(f"最优卖价: ${best_ask:.4f}")
                        
                        # 价格过滤器：只在 0.50 ~ 0.70 之间入场
                        if 0.50 <= best_ask <= 0.70:
                            size = round(TRADE_AMOUNT / best_ask, 2)
                            print(f"✅ 满足条件，准备买入 {size} tokens")
                            
                            order_args = OrderArgs(
                                token_id=target_token,
                                price=best_ask,
                                size=size,
                                side='BUY',
                            )
                            signed_order = client.create_order(order_args)
                            resp = client.post_order(signed_order, OrderType.FOK)
                            
                            if resp.get('status') == 'matched':
                                current_position = {
                                    'token_id': target_token,
                                    'size': size,
                                    'buy_price': best_ask,
                                    'window_end': window_end
                                }
                                msg = f"""🎯 【龙虾火控 - 提前布局入场】
━━━━━━━━━━━━━━━━━━━━━
方向: {sig} (RSI:{rsi:.1f})
买入: ${TRADE_AMOUNT:.2f} @ ${best_ask:.4f}
数量: {size} tokens
预期将在 T-30 平仓
━━━━━━━━━━━━━━━━━━━━━"""
                                print(msg)
                                send_tg(msg)
                        else:
                            print(f"❌ 价格不在 0.50~0.70 区间，放弃")
                
            time.sleep(5)
            
        except Exception as e:
            print(f"循环错误: {e}")
            time.sleep(5)

if __name__ == '__main__':
    run_loop()
