import time, requests, logging, os
from utils import get_poly_price, send_telegram_msg, get_trading_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArbBrain")

BTC_TOKEN_ID = "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b"

def run_scanner():
    # 🚨 给 Web 进程 15 秒启动缓冲
    logger.info("⏳ 等待 Web 进程启动...")
    time.sleep(15)
    
    # 尝试鉴权测试
    logger.info("🔑 正在进行 L2 鉴权测试...")
    client = get_trading_client()
    if client: logger.info("✅ L2 鉴权通过！")
    else: logger.error("❌ 鉴权失败，请检查私钥和地址")

    while True:
        try:
            res = requests.get("http://127.0.0.1:8080/data", timeout=5).json()
            binance_p = res[0]['close']
            bid, ask = get_poly_price(BTC_TOKEN_ID)
            
            if ask:
                logger.info(f"📊 B: {binance_p} | P: {ask}")
                if binance_p > 105000 and ask < 0.55:
                    send_telegram_msg(f"🎯 机会触发! B:{binance_p} P:{ask}")
            
            time.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_scanner()
