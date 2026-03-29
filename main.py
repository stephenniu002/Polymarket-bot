import time
import requests
import logging
import os
from utils import send_telegram_msg, get_poly_price

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ArbScanner")

# --- 🎯 目标市场配置 ---
# 示例：Bitcoin Price in March (YES/NO) 
# 你可以在 https://clob.polymarket.com/markets 找到这些 ID
TARGET_MARKETS = {
    "BTC_UP": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b", # 举例 ID
}

BINANCE_INTERNAL_URL = "http://localhost:8080/data"

def start_scanning():
    logger.info("🚀 Worker 扫描器启动成功，正在接入 Polymarket CLOB...")
    
    while True:
        try:
            # 1. 获取币安实时参考价
            try:
                res = requests.get(BINANCE_INTERNAL_URL, timeout=3).json()
                binance_p = float(res[-1]['close'])
            except:
                logger.warning("🕒 等待 Web 看板数据就绪...")
                time.sleep(5)
                continue

            # 2. 遍历监控市场 (目前以 BTC_UP 为例)
            for name, token_id in TARGET_MARKETS.items():
                bid, ask = get_poly_price(token_id)
                
                if bid is not None:
                    # 这里的逻辑是核心：当 Binance 价格 > 某个点位，Poly 应该涨
                    # 简化示例：监控 Poly 卖一价是否异常偏移
                    logger.info(f"📊 [{name}] Binance: {binance_p} | Poly Ask: {ask}")
                    
                    # 触发逻辑示例：
                    # if binance_p > 100000 and ask < 0.40:
                    #    send_telegram_msg(f"🚨 套利机会！Binance 破10w但 Poly 卖一价才 {ask}")

            time.sleep(5) # 频率控制

        except Exception as e:
            logger.error(f"扫描异常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    start_scanning()
