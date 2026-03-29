import time
import os
import requests
import logging
from utils import send_telegram_msg, calculate_kelly

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Scanner")

# 配置参数
CHECK_INTERVAL = 10  # 每10秒扫描一次
DASHBOARD_URL = "http://localhost:8080/data"  # 内部访问地址

def fetch_binance_price():
    """从自有的 Dashboard 接口获取最新实时价"""
    try:
        # 注意：在 Railway 内部，web 和 worker 共享环境，通常用 localhost
        res = requests.get(DASHBOARD_URL, timeout=5)
        data = res.json()
        if data and len(data) > 0:
            return float(data[-1]['close'])
    except:
        return None

def start_scanning():
    logger.info("🚀 Polymarket 扫描器 (Worker) 已启动...")
    send_telegram_msg("🔔 *Polymarket 扫描器已在 Railway 上线！*")

    while True:
        try:
            # 1. 获取币安实时价
            binance_price = fetch_binance_price()
            
            # 2. 模拟获取 Polymarket 价格 (下一步我们将接入真实的 Poly API)
            # 这里先写死一个逻辑，方便你测试
            logger.info(f"🔎 正在扫描... 当前币安参考价: {binance_price}")
            
            # TODO: 接入 Polymarket Orderbook API 
            # if 发现价差 > 阈值:
            #    send_telegram_msg(f"🎯 发现机会！\n价格: {binance_price}\n建议仓位: ...")

            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"扫描循环异常: {e}")
            time.sleep(20)

if __name__ == "__main__":
    start_scanning()
