"""
双策略对比可视化 (Dual Strategy Visualization)
- 策略A：提前布局 (T+2~4min, 0.48~0.72入场)
- 策略B：反转猎手 (0.20~0.30入场, 止盈0.50, 止损0.15)
"""
import requests
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib import rcParams
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# 中文字体
rcParams['font.family'] = ['Noto Sans CJK SC', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False

def fetch_klines(symbol='BTCUSDT', interval='1m', limit=120):
    r = requests.get(
        'https://api.binance.com/api/v3/klines',
        params={'symbol': symbol, 'interval': interval, 'limit': limit},
        timeout=10
    )
    data = r.json()
    df = pd.DataFrame(data, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','qav','num_trades','taker_buy_base','taker_buy_quote','ignore'
    ])
    for c in ['open','high','low','close','volume']:
        df[c] = df[c].astype(float)
    return df

def calc_rsi(closes, period=14):
    delta = pd.Series(closes).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_momentum(closes, period=5):
    s = pd.Series(closes)
    return (s - s.shift(period)) / s.shift(period) * 100

def simulate_dual_strategies(df):
    closes = df['close'].values
    rsi = calc_rsi(closes)
    mom = calc_momentum(closes)

    trades_A = []
    trades_B = []
    pos_A = None
    pos_B = None

    for w_start in range(0, len(df) - 5, 5):
        w_end = w_start + 5
        for i in range(w_start, min(w_end, len(df))):
            elapsed = i - w_start
            remaining = w_end - i
            r = rsi.iloc[i] if not np.isnan(rsi.iloc[i]) else 50
            m = mom.iloc[i] if not np.isnan(mom.iloc[i]) else 0
            
            # 模拟实际价格变化带来的 token 价格变化
            actual_change = (closes[i] - closes[w_start]) / closes[w_start] * 100
            token_up = 0.50 + min(max(actual_change * 10, -0.45), 0.45)
            token_down = 0.50 - min(max(actual_change * 10, -0.45), 0.45)

            # ── 策略A：提前布局 ──
            if not pos_A and 2 <= elapsed <= 4:
                if r > 60 and m > 0.05 and 0.48 <= token_up <= 0.72:
                    pos_A = {'entry_bar': i, 'price': token_up, 'dir': 'UP', 'size': 5.0/token_up, 'w_end': w_end}
                elif r < 40 and m < -0.05 and 0.48 <= token_down <= 0.72:
                    pos_A = {'entry_bar': i, 'price': token_down, 'dir': 'DOWN', 'size': 5.0/token_down, 'w_end': w_end}

            if pos_A and remaining == 1 and pos_A['w_end'] == w_end:
                final_change = (closes[w_end-1] - closes[w_start]) / closes[w_start] * 100
                exit_price = 0.50 + min(max(final_change * 10, -0.45), 0.45) if pos_A['dir'] == 'UP' else 0.50 - min(max(final_change * 10, -0.45), 0.45)
                
                pnl_75 = (exit_price - pos_A['price']) * (pos_A['size'] * 0.75)
                final_val = 1.0 if (pos_A['dir'] == 'UP' and final_change >= 0) or (pos_A['dir'] == 'DOWN' and final_change < 0) else 0.0
                pnl_25 = (final_val - pos_A['price']) * (pos_A['size'] * 0.25)
                
                trades_A.append({'pnl': pnl_75 + pnl_25, 'win': (pnl_75 + pnl_25) > 0})
                pos_A = None

            # ── 策略B：反转猎手 ──
            if not pos_B:
                # 检查 UP token 是否在 0.20~0.30 且有反转信号
                if 0.20 <= token_up <= 0.30 and r < 35 and m > 0:
                    pos_B = {'entry_bar': i, 'price': token_up, 'dir': 'UP', 'size': 5.0/token_up, 'w_end': w_end}
                # 检查 DOWN token
                elif 0.20 <= token_down <= 0.30 and r > 65 and m < 0:
                    pos_B = {'entry_bar': i, 'price': token_down, 'dir': 'DOWN', 'size': 5.0/token_down, 'w_end': w_end}

            if pos_B and pos_B['w_end'] == w_end:
                curr_price = token_up if pos_B['dir'] == 'UP' else token_down
                
                # 止盈 / 止损 / T-60
                if curr_price >= 0.50 or curr_price <= 0.15 or remaining == 1:
                    sell_size = pos_B['size'] * 0.75
                    pnl_75 = (curr_price - pos_B['price']) * sell_size
                    
                    final_change = (closes[w_end-1] - closes[w_start]) / closes[w_start] * 100
                    final_val = 1.0 if (pos_B['dir'] == 'UP' and final_change >= 0) or (pos_B['dir'] == 'DOWN' and final_change < 0) else 0.0
                    pnl_25 = (final_val - pos_B['price']) * (pos_B['size'] * 0.25)
                    
                    trades_B.append({'pnl': pnl_75 + pnl_25, 'win': (pnl_75 + pnl_25) > 0})
                    pos_B = None

    return trades_A, trades_B

print("获取数据并模拟双策略...")
df = fetch_klines('BTCUSDT', '1m', 120)
trades_A, trades_B = simulate_dual_strategies(df)

# 绘图
fig = plt.figure(figsize=(14, 8))
fig.patch.set_facecolor('#0d1117')
ax = fig.add_subplot(111)
ax.set_facecolor('#161b22')
ax.tick_params(colors='#e6edf3')
for spine in ax.spines.values():
    spine.set_edgecolor('#21262d')

def plot_pnl(trades, color, label):
    cum = []
    run = 0
    for t in trades:
        run += t['pnl']
        cum.append(run)
    if cum:
        ax.plot(range(len(cum)), cum, color=color, linewidth=2, marker='o', label=f"{label} (胜率 {sum(1 for t in trades if t['win'])/len(trades)*100:.0f}%, 盈亏 ${run:+.2f})")

plot_pnl(trades_A, '#58a6ff', '策略A: 提前布局 (T+2~4min)')
plot_pnl(trades_B, '#bc8cff', '策略B: 反转猎手 (0.20~0.30入场)')

ax.axhline(0, color='#21262d', linewidth=1)
ax.set_title('Polymarket 双策略累计盈亏对比 (模拟最近 120 分钟)', color='#e6edf3', fontsize=14, pad=15)
ax.set_ylabel('累计盈亏 (USDC)', color='#e6edf3', fontsize=11)
ax.set_xlabel('交易笔数', color='#e6edf3', fontsize=11)
ax.legend(facecolor='#161b22', labelcolor='#e6edf3', edgecolor='#21262d', fontsize=10)
ax.grid(color='#21262d', linewidth=0.5, alpha=0.5)

out = '/home/ubuntu/Polymarket-bot/dual_strategy_comparison.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='#0d1117')
plt.close()
print(f"✅ 图表已保存: {out}")
