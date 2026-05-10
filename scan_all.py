import sys
sys.path.insert(0, '/home/ubuntu/Polymarket-bot')
import bot_live, time

print('当前7币种市场价格扫描:')
print('{:<6} {:<10} {:<10} {:<10} {:<10} {}'.format(
    '币种', 'UP基础价', 'UP ask', 'DOWN基础价', 'DOWN ask', '入场可能'))
print('-'*70)
for coin in bot_live.COINS:
    m = bot_live.get_market(coin)
    if not m:
        print('{:<6} 无市场'.format(coin.upper()))
        continue
    ua = bot_live.get_best_ask(m['up_token'])
    da = bot_live.get_best_ask(m['down_token'])
    up_ok = ua and 0.01 <= ua <= 0.30
    dn_ok = da and 0.01 <= da <= 0.30
    flag = '✅ UP可入场' if up_ok else ('✅ DOWN可入场' if dn_ok else '❌ 无机会')
    print('{:<6} {:<10.3f} {:<10} {:<10.3f} {:<10} {}'.format(
        coin.upper(), m['up_price'], str(ua), m['down_price'], str(da), flag))
    time.sleep(0.5)
