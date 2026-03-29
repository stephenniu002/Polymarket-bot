import time, requests, logging, os
from utils import get_poly_price, send_telegram_msg, calculate_kelly_bet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArbBrain")

# 你的真实 Token ID
BTC_TOKEN_ID = "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b"

def run_scanner():
    logger.info("🚀 Worker 启动...")
    # 给 Web 进程留出启动时间
    time.sleep(10)
    
    while True:
        try:
            # 内部通信，使用 127.0.0.1 避开网关
            res = requests.get("http://127.0.0.1:8080/data", timeout=2).json()
            if not res: continue
            
            binance_p = res[0]['close']
            bid, ask = get_poly_price(BTC_TOKEN_ID)
            
            if ask:
                logger.info(f"📊 B: {binance_p} | P: {ask}")
                # 示例触发逻辑
                if binance_p > 105000 and ask < 0.55:
                    send_telegram_msg(f"🚨 机会! B:{binance_p} P:{ask}")
                    time.sleep(60)

            time.sleep(5)
        except Exception as e:
            logger.debug(f"Waiting for hub... {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_scanner()
