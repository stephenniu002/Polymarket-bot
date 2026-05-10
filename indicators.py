"""
技术指标计算模块 (RSI + 动量)
基于 Binance 1分钟 K线数据
"""
import requests
import numpy as np
import pandas as pd

def get_binance_klines(symbol='BTCUSDT', interval='1m', limit=20):
    """获取 Binance K线数据"""
    try:
        r = requests.get(
            'https://api.binance.com/api/v3/klines',
            params={'symbol': symbol, 'interval': interval, 'limit': limit},
            timeout=5
        )
        data = r.json()
        # [Open time, Open, High, Low, Close, Volume, ...]
        closes = [float(k[4]) for k in data]
        return closes
    except Exception as e:
        print(f"获取 K线失败: {e}")
        return []

def calculate_rsi(prices, period=14):
    """计算 RSI 指标"""
    if len(prices) < period + 1:
        return 50.0
    
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    if down == 0:
        return 100.0
    if up == 0:
        return 0.0
        
    rs = up / down
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
            
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        
        if down == 0:
            rsi[i] = 100.
        else:
            rs = up / down
            rsi[i] = 100. - 100. / (1. + rs)
            
    return rsi[-1]

def calculate_momentum(prices, period=5):
    """计算动量 (ROC)"""
    if len(prices) < period + 1:
        return 0.0
    
    return (prices[-1] - prices[-period-1]) / prices[-period-1] * 100

def get_signals(symbol='BTCUSDT'):
    """获取综合信号"""
    closes = get_binance_klines(symbol, limit=20)
    if not closes:
        return 'NEUTRAL', 50.0, 0.0
        
    rsi = calculate_rsi(closes, period=14)
    mom = calculate_momentum(closes, period=5)
    
    # 信号逻辑
    # RSI > 60 且 动量 > 0.05% -> UP
    # RSI < 40 且 动量 < -0.05% -> DOWN
    if rsi > 60 and mom > 0.05:
        return 'UP', rsi, mom
    elif rsi < 40 and mom < -0.05:
        return 'DOWN', rsi, mom
    else:
        return 'NEUTRAL', rsi, mom

if __name__ == '__main__':
    # 测试
    sig, rsi, mom = get_signals('BTCUSDT')
    print(f"BTC 信号: {sig} | RSI: {rsi:.2f} | 动量: {mom:+.3f}%")
