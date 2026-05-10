"""
双策略 24 小时完整回测
策略A：提前布局 (T+2~4min, 0.48~0.72入场, T-60卖75%)
策略B：反转猎手 (0.01~0.30入场, T-90卖75%, 小单$2)
数据：Binance BTC 1分钟K线，过去1440根（24小时）
"""
import requests
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib import rcParams
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

rcParams['font.family'] = ['Noto Sans CJK SC', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False

COLORS = {
    'bg': '#0d1117', 'panel': '#161b22', 'text': '#e6edf3',
    'green': '#3fb950', 'red': '#f85149', 'blue': '#58a6ff',
    'yellow': '#d29922', 'purple': '#bc8cff', 'orange': '#f0883e',
    'grid': '#21262d', 'teal': '#39d353'
}

# ── 获取数据 ──────────────────────────────────────────────
def fetch_klines_24h(symbol='BTCUSDT'):
    """分两批获取 1440 根 1分钟K线"""
    all_data = []
    for offset in [1440, 720, 0]:
        r = requests.get(
            'https://api.binance.com/api/v3/klines',
            params={'symbol': symbol, 'interval': '1m', 'limit': 720,
                    'endTime': int((datetime.now() - timedelta(minutes=offset)).timestamp() * 1000)},
            timeout=15
        )
        all_data = r.json() + all_data
    df = pd.DataFrame(all_data, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','qav','num_trades','taker_buy_base','taker_buy_quote','ignore'
    ])
    df = df.drop_duplicates('open_time').sort_values('open_time').reset_index(drop=True)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    for c in ['open','high','low','close','volume']:
        df[c] = df[c].astype(float)
    return df

# ── 指标计算 ──────────────────────────────────────────────
def calc_rsi(closes, period=14):
    delta = pd.Series(closes).diff()
    gain = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100/(1+rs)).fillna(50)

def calc_momentum(closes, period=5):
    s = pd.Series(closes)
    return ((s - s.shift(period)) / s.shift(period) * 100).fillna(0)

# ── Token 价格模拟 ─────────────────────────────────────────
def sim_token_price(change_pct, direction='UP', base=0.50):
    """根据 BTC 涨跌幅模拟 token 价格"""
    if direction == 'UP':
        return min(max(base + change_pct * 8, 0.01), 0.99)
    else:
        return min(max(base - change_pct * 8, 0.01), 0.99)

# ── 策略A 回测 ────────────────────────────────────────────
def backtest_strategy_A(df, trade_amount=5.0):
    closes = df['close'].values
    rsi = calc_rsi(closes).values
    mom = calc_momentum(closes).values
    trades = []
    pos = None

    for w in range(0, len(df) - 5, 5):
        w_end = w + 5
        open_price = closes[w]

        for i in range(w, min(w_end, len(df))):
            elapsed = i - w
            remaining = w_end - i
            r, m = rsi[i], mom[i]

            # T+2~T+4 入场
            if not pos and 2 <= elapsed <= 4:
                change_now = (closes[i] - open_price) / open_price * 100
                if r > 60 and m > 0.05:
                    token_p = sim_token_price(change_now, 'UP')
                    if 0.48 <= token_p <= 0.72:
                        pos = {'entry': i, 'price': token_p, 'dir': 'UP',
                               'size': trade_amount/token_p, 'w_end': w_end, 'open': open_price}
                elif r < 40 and m < -0.05:
                    token_p = sim_token_price(change_now, 'DOWN')
                    if 0.48 <= token_p <= 0.72:
                        pos = {'entry': i, 'price': token_p, 'dir': 'DOWN',
                               'size': trade_amount/token_p, 'w_end': w_end, 'open': open_price}

            # T-60 卖出 75%
            if pos and remaining == 1 and pos['w_end'] == w_end:
                final_chg = (closes[w_end-1] - pos['open']) / pos['open'] * 100
                exit_p = sim_token_price(final_chg, pos['dir'])

                pnl_75 = (exit_p - pos['price']) * pos['size'] * 0.75
                final_val = 1.0 if (
                    (pos['dir']=='UP' and final_chg >= 0) or
                    (pos['dir']=='DOWN' and final_chg < 0)
                ) else 0.0
                pnl_25 = (final_val - pos['price']) * pos['size'] * 0.25
                total = pnl_75 + pnl_25

                trades.append({
                    'window': w//5, 'time': df['open_time'].iloc[i],
                    'dir': pos['dir'], 'entry': pos['price'],
                    'exit75': exit_p, 'final': final_val,
                    'pnl': total, 'win': total > 0,
                    'rsi': r, 'mom': m,
                })
                pos = None

    return pd.DataFrame(trades)

# ── 策略B 回测 ────────────────────────────────────────────
def backtest_strategy_B(df, trade_amount=2.0):
    closes = df['close'].values
    rsi = calc_rsi(closes).values
    mom = calc_momentum(closes).values
    trades = []
    pos = None

    for w in range(0, len(df) - 5, 5):
        w_end = w + 5
        open_price = closes[w]

        for i in range(w, min(w_end, len(df))):
            elapsed = i - w
            remaining = w_end - i
            r, m = rsi[i], mom[i]

            # 检查平仓条件
            if pos and pos['w_end'] == w_end:
                curr_chg = (closes[i] - pos['open']) / pos['open'] * 100
                curr_p = sim_token_price(curr_chg, pos['dir'])

                close_reason = None
                if curr_p >= 0.50:
                    close_reason = '止盈'
                elif curr_p <= 0.005:
                    close_reason = '止损'
                elif remaining <= 1:  # T-90 (最后1.5根K线)
                    close_reason = 'T-90'

                if close_reason:
                    final_chg = (closes[w_end-1] - pos['open']) / pos['open'] * 100
                    final_val = 1.0 if (
                        (pos['dir']=='UP' and final_chg >= 0) or
                        (pos['dir']=='DOWN' and final_chg < 0)
                    ) else 0.0
                    pnl_75 = (curr_p - pos['price']) * pos['size'] * 0.75
                    pnl_25 = (final_val - pos['price']) * pos['size'] * 0.25
                    total = pnl_75 + pnl_25

                    trades.append({
                        'window': w//5, 'time': df['open_time'].iloc[i],
                        'dir': pos['dir'], 'entry': pos['price'],
                        'exit75': curr_p, 'final': final_val,
                        'pnl': total, 'win': total > 0,
                        'close_reason': close_reason,
                        'rsi': r, 'mom': m,
                    })
                    pos = None
                    continue

            # 入场：T+0~T+4，价格 0.01~0.30，反转信号
            if not pos and elapsed <= 4 and remaining > 1:
                change_now = (closes[i] - open_price) / open_price * 100

                # 检查 UP token
                token_up = sim_token_price(change_now, 'UP')
                token_dn = sim_token_price(change_now, 'DOWN')

                score_up = 0
                if 0.01 <= token_up <= 0.30:
                    if r < 35: score_up += 2
                    elif r < 40: score_up += 1
                    if i > 0 and rsi[i] > rsi[i-1]: score_up += 2
                    if m > 0: score_up += 1
                    if token_up <= 0.10: score_up += 2  # 超低价加分
                    if score_up >= 4:
                        pos = {'entry': i, 'price': token_up, 'dir': 'UP',
                               'size': trade_amount/token_up, 'w_end': w_end, 'open': open_price}
                        continue

                score_dn = 0
                if 0.01 <= token_dn <= 0.30:
                    if r > 65: score_dn += 2
                    elif r > 60: score_dn += 1
                    if i > 0 and rsi[i] < rsi[i-1]: score_dn += 2
                    if m < 0: score_dn += 1
                    if token_dn <= 0.10: score_dn += 2
                    if score_dn >= 4:
                        pos = {'entry': i, 'price': token_dn, 'dir': 'DOWN',
                               'size': trade_amount/token_dn, 'w_end': w_end, 'open': open_price}

    return pd.DataFrame(trades)

# ── 主程序 ────────────────────────────────────────────────
print("📡 获取 Binance BTC 24小时 1分钟K线数据...")
df = fetch_klines_24h('BTCUSDT')
print(f"✅ 获取 {len(df)} 根K线，时间范围: {df['open_time'].iloc[0]} → {df['open_time'].iloc[-1]}")

print("🔄 运行策略A回测（提前布局）...")
res_A = backtest_strategy_A(df, trade_amount=5.0)
print(f"   策略A: {len(res_A)} 笔交易")

print("🔄 运行策略B回测（反转猎手）...")
res_B = backtest_strategy_B(df, trade_amount=2.0)
print(f"   策略B: {len(res_B)} 笔交易")

# ── 统计 ──────────────────────────────────────────────────
def stats(df_t, name):
    if df_t.empty:
        print(f"{name}: 无交易")
        return {}
    wins = df_t['win'].sum()
    total = len(df_t)
    pnl = df_t['pnl'].sum()
    max_dd = (df_t['pnl'].cumsum() - df_t['pnl'].cumsum().cummax()).min()
    print(f"\n{'='*45}")
    print(f"  {name}")
    print(f"{'='*45}")
    print(f"  总交易笔数: {total}")
    print(f"  胜率:       {wins/total*100:.1f}% ({wins}胜/{total-wins}负)")
    print(f"  累计盈亏:   ${pnl:+.4f}")
    print(f"  平均每笔:   ${pnl/total:+.4f}")
    print(f"  最大回撤:   ${max_dd:.4f}")
    print(f"  最大单笔盈: ${df_t['pnl'].max():+.4f}")
    print(f"  最大单笔亏: ${df_t['pnl'].min():+.4f}")
    return {'wins': wins, 'total': total, 'pnl': pnl, 'max_dd': max_dd}

st_A = stats(res_A, "策略A：提前布局 (T+2~4min, $5/笔)")
st_B = stats(res_B, "策略B：反转猎手 (0.01~0.30, $2/笔)")

# ── 绘图 ──────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 16))
fig.patch.set_facecolor(COLORS['bg'])
gs = gridspec.GridSpec(4, 2, hspace=0.45, wspace=0.3,
                        height_ratios=[2, 1.5, 1.5, 1.5])

# 1. BTC 价格走势（全24小时）
ax_price = fig.add_subplot(gs[0, :])
ax_price.set_facecolor(COLORS['panel'])
for spine in ax_price.spines.values():
    spine.set_edgecolor(COLORS['grid'])
ax_price.tick_params(colors=COLORS['text'], labelsize=8)

x = range(len(df))
ax_price.plot(x, df['close'].values, color=COLORS['blue'], linewidth=1, alpha=0.9)
ax_price.fill_between(x, df['close'].values, df['close'].min(),
                       alpha=0.1, color=COLORS['blue'])

# 标记策略A入场点
if not res_A.empty:
    for _, t in res_A.iterrows():
        idx = df[df['open_time'] == t['time']].index
        if len(idx) > 0:
            c = COLORS['green'] if t['win'] else COLORS['red']
            ax_price.scatter(idx[0], df['close'].iloc[idx[0]],
                             color=c, s=25, zorder=5, alpha=0.8, marker='^')

# 标记策略B入场点
if not res_B.empty:
    for _, t in res_B.iterrows():
        idx = df[df['open_time'] == t['time']].index
        if len(idx) > 0:
            c = COLORS['green'] if t['win'] else COLORS['red']
            ax_price.scatter(idx[0], df['close'].iloc[idx[0]],
                             color=c, s=25, zorder=5, alpha=0.8, marker='D')

# X轴时间标签（每2小时）
tick_step = 120
xticks = list(range(0, len(df), tick_step))
xlabels = [df['open_time'].iloc[i].strftime('%H:%M') for i in xticks]
ax_price.set_xticks(xticks)
ax_price.set_xticklabels(xlabels, fontsize=7, color=COLORS['text'])
ax_price.set_ylabel('BTC/USDT', color=COLORS['text'], fontsize=9)
ax_price.set_title(
    f'BTC 24小时走势  |  ▲策略A入场  ◆策略B入场  (绿=盈利  红=亏损)',
    color=COLORS['text'], fontsize=11, pad=8)
ax_price.grid(axis='y', color=COLORS['grid'], linewidth=0.4, alpha=0.5)

# 2. 策略A 累计盈亏
ax_A = fig.add_subplot(gs[1, 0])
ax_A.set_facecolor(COLORS['panel'])
for spine in ax_A.spines.values():
    spine.set_edgecolor(COLORS['grid'])
ax_A.tick_params(colors=COLORS['text'], labelsize=8)

if not res_A.empty:
    cum_A = res_A['pnl'].cumsum().values
    ax_A.plot(range(len(cum_A)), cum_A, color=COLORS['blue'], linewidth=2)
    ax_A.fill_between(range(len(cum_A)), cum_A, 0,
                       where=cum_A >= 0, alpha=0.2, color=COLORS['green'])
    ax_A.fill_between(range(len(cum_A)), cum_A, 0,
                       where=cum_A < 0, alpha=0.2, color=COLORS['red'])
    for i, v in enumerate(cum_A):
        ax_A.scatter(i, v, color=COLORS['green'] if v >= 0 else COLORS['red'], s=20, zorder=5)
    ax_A.axhline(0, color=COLORS['grid'], linewidth=0.8)
    wr = st_A.get('wins',0)/st_A.get('total',1)*100
    ax_A.set_title(f'策略A 累计盈亏 | {st_A.get("total",0)}笔 | 胜率{wr:.0f}% | 总计${st_A.get("pnl",0):+.2f}',
                   color=COLORS['text'], fontsize=9)
ax_A.set_ylabel('USDC', color=COLORS['text'], fontsize=8)
ax_A.set_xlabel('交易笔数', color=COLORS['text'], fontsize=8)
ax_A.grid(color=COLORS['grid'], linewidth=0.4, alpha=0.5)

# 3. 策略B 累计盈亏
ax_B = fig.add_subplot(gs[1, 1])
ax_B.set_facecolor(COLORS['panel'])
for spine in ax_B.spines.values():
    spine.set_edgecolor(COLORS['grid'])
ax_B.tick_params(colors=COLORS['text'], labelsize=8)

if not res_B.empty:
    cum_B = res_B['pnl'].cumsum().values
    ax_B.plot(range(len(cum_B)), cum_B, color=COLORS['purple'], linewidth=2)
    ax_B.fill_between(range(len(cum_B)), cum_B, 0,
                       where=cum_B >= 0, alpha=0.2, color=COLORS['green'])
    ax_B.fill_between(range(len(cum_B)), cum_B, 0,
                       where=cum_B < 0, alpha=0.2, color=COLORS['red'])
    for i, v in enumerate(cum_B):
        ax_B.scatter(i, v, color=COLORS['green'] if v >= 0 else COLORS['red'], s=20, zorder=5)
    ax_B.axhline(0, color=COLORS['grid'], linewidth=0.8)
    wr_B = res_B['win'].sum()/len(res_B)*100
    ax_B.set_title(f'策略B 累计盈亏 | {len(res_B)}笔 | 胜率{wr_B:.0f}% | 总计${res_B["pnl"].sum():+.2f}',
                   color=COLORS['text'], fontsize=9)
ax_B.set_ylabel('USDC', color=COLORS['text'], fontsize=8)
ax_B.set_xlabel('交易笔数', color=COLORS['text'], fontsize=8)
ax_B.grid(color=COLORS['grid'], linewidth=0.4, alpha=0.5)

# 4. 每笔盈亏分布（策略A）
ax_dist_A = fig.add_subplot(gs[2, 0])
ax_dist_A.set_facecolor(COLORS['panel'])
for spine in ax_dist_A.spines.values():
    spine.set_edgecolor(COLORS['grid'])
ax_dist_A.tick_params(colors=COLORS['text'], labelsize=8)

if not res_A.empty:
    colors_bar = [COLORS['green'] if v > 0 else COLORS['red'] for v in res_A['pnl']]
    ax_dist_A.bar(range(len(res_A)), res_A['pnl'].values, color=colors_bar, alpha=0.85, width=0.8)
    ax_dist_A.axhline(0, color=COLORS['grid'], linewidth=0.8)
    ax_dist_A.set_title('策略A 每笔盈亏', color=COLORS['text'], fontsize=9)
ax_dist_A.set_ylabel('USDC', color=COLORS['text'], fontsize=8)
ax_dist_A.set_xlabel('交易笔数', color=COLORS['text'], fontsize=8)
ax_dist_A.grid(axis='y', color=COLORS['grid'], linewidth=0.4, alpha=0.5)

# 5. 每笔盈亏分布（策略B）
ax_dist_B = fig.add_subplot(gs[2, 1])
ax_dist_B.set_facecolor(COLORS['panel'])
for spine in ax_dist_B.spines.values():
    spine.set_edgecolor(COLORS['grid'])
ax_dist_B.tick_params(colors=COLORS['text'], labelsize=8)

if not res_B.empty:
    colors_bar_B = [COLORS['green'] if v > 0 else COLORS['red'] for v in res_B['pnl']]
    ax_dist_B.bar(range(len(res_B)), res_B['pnl'].values, color=colors_bar_B, alpha=0.85, width=0.8)
    ax_dist_B.axhline(0, color=COLORS['grid'], linewidth=0.8)
    ax_dist_B.set_title('策略B 每笔盈亏', color=COLORS['text'], fontsize=9)
ax_dist_B.set_ylabel('USDC', color=COLORS['text'], fontsize=8)
ax_dist_B.set_xlabel('交易笔数', color=COLORS['text'], fontsize=8)
ax_dist_B.grid(axis='y', color=COLORS['grid'], linewidth=0.4, alpha=0.5)

# 6. 综合对比统计表
ax_table = fig.add_subplot(gs[3, :])
ax_table.set_facecolor(COLORS['panel'])
ax_table.axis('off')

pnl_A = st_A.get('pnl', 0)
pnl_B = res_B['pnl'].sum() if not res_B.empty else 0
wr_A = st_A.get('wins',0)/st_A.get('total',1)*100 if st_A.get('total',0) > 0 else 0
wr_B_val = res_B['win'].sum()/len(res_B)*100 if not res_B.empty else 0

table_data = [
    ['指标', '策略A：提前布局', '策略B：反转猎手', '合并'],
    ['交易笔数', str(st_A.get('total',0)), str(len(res_B)), str(st_A.get('total',0)+len(res_B))],
    ['胜率', f'{wr_A:.1f}%', f'{wr_B_val:.1f}%', f'{(st_A.get("wins",0)+res_B["win"].sum() if not res_B.empty else 0)/(st_A.get("total",1)+len(res_B)+0.001)*100:.1f}%'],
    ['累计盈亏', f'${pnl_A:+.4f}', f'${pnl_B:+.4f}', f'${pnl_A+pnl_B:+.4f}'],
    ['每笔均值', f'${pnl_A/max(st_A.get("total",1),1):+.4f}', f'${pnl_B/max(len(res_B),1):+.4f}', '-'],
    ['最大回撤', f'${st_A.get("max_dd",0):.4f}', f'${(res_B["pnl"].cumsum()-res_B["pnl"].cumsum().cummax()).min():.4f}' if not res_B.empty else '$0', '-'],
    ['单笔金额', '$5.00', '$2.00 (小单)', '-'],
    ['入场条件', 'RSI+动量 T+2~4min', '价格0.01~0.30 反转信号', '-'],
    ['平仓规则', 'T-60 卖75%+25%结算', 'T-90 卖75%+25%结算', '-'],
]

tbl = ax_table.table(cellText=table_data[1:], colLabels=table_data[0],
                      cellLoc='center', loc='center',
                      bbox=[0, 0, 1, 1])
tbl.auto_set_font_size(False)
tbl.set_fontsize(9)

for (row, col), cell in tbl.get_celld().items():
    cell.set_facecolor(COLORS['panel'])
    cell.set_edgecolor(COLORS['grid'])
    cell.set_text_props(color=COLORS['text'])
    if row == 0:
        cell.set_facecolor('#1f2937')
        cell.set_text_props(color=COLORS['yellow'], fontweight='bold')
    if col == 3 and row > 0:
        val_text = cell.get_text().get_text()
        if '+' in val_text:
            cell.set_text_props(color=COLORS['green'])
        elif '-' in val_text and '$' in val_text:
            cell.set_text_props(color=COLORS['red'])

ax_table.set_title('24小时回测综合统计', color=COLORS['text'], fontsize=10, pad=8)

# 总标题
fig.suptitle(
    f'Polymarket 双策略 24小时回测报告  |  BTC 5分钟市场  |  {datetime.now().strftime("%Y-%m-%d %H:%M")}',
    color=COLORS['text'], fontsize=13, fontweight='bold', y=0.99
)

out = '/home/ubuntu/Polymarket-bot/backtest_24h_report.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=COLORS['bg'])
plt.close()
print(f"\n✅ 图表已保存: {out}")
