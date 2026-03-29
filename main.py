import time, requests, logging
from utils import get_poly_price, send_telegram_msg, calculate_kelly_bet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ArbBrain")

# --- 🎯 实战配置：BTC 破 10.5w 预测市场 (示例 ID，请按前文方法替换) ---
BTC_MARKET = {
    "name": "BTC > $105,000",
    "token_id": "0x21131102657e4e137b1297e21a2c7a36372c0500f40958195a623f9909249e0b", # 请替换为真实 ID
    "trigger_price": 105000
}

INTERNAL_DATA_URL = "http://localhost:8080/data"

def run_scanner():
    logger.info("🚀 套利扫描器(Worker)开始 24/7 监控...")
    while True:
        try:
            # 1. 获取币安实时参考价
            res = requests.get(INTERNAL_DATA_URL, timeout=3).json()
            if not res: 
                time.sleep(5); continue
            binance_p = float(res[-1]['close'])

            # 2. 获取 Poly 盘口
            bid, ask = get_poly_price(BTC_MARKET["token_id"])
            
            if ask is not None:
                logger.info(f"📊 Binance: {binance_p} | Poly Ask: {ask}")
                
                # --- 策略：Binance 价格已突破，但 Poly YES 还没涨过 0.60 ---
                if binance_p > BTC_MARKET["trigger_price"] and ask < 0.55:
                    bet = calculate_kelly_bet(0.65, ask) # 假设 65% 概率
                    msg = (
                        f"🚨 *套利警报!*\n\n"
                        f"📉 币安已突破: `${binance_p}`\n"
                        f"💎 Poly 卖价滞后: `{ask}`\n"
                        f"💰 建议仓位: `${bet}`\n"
                        f"🔗 [立即下单](https://polymarket.com/)"
                    )
                    send_telegram_msg(msg)
                    time.sleep(60) # 报警后冷却 1 分钟

            time.sleep(5)
        except Exception as e:
            logger.error(f"Worker 异常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_scanner()
