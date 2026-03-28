import os
import time
import requests
import webbrowser
from datetime import datetime

# ================= 核心配置区域 =================
TELEGRAM_TOKEN = "7788042130:AAFJZo9LVP1fmjZjfn8wOvnCXBzCJMIU2Wg"
TELEGRAM_CHAT_ID = "7788042130:"  # ⚠️ 这一排一定要改成你的真实数字ID，保留双引号！

COOLDOWN = 600            # 市场冷却时间：10分钟 (秒)
PRICE_DELTA = 0.01        # 二次触发阈值：如果总价变动超过 1% 即便在冷却期内也提醒
TG_RATE_LIMIT = 1         # Telegram 限速：防止被 API 屏蔽
BROWSER_COOLDOWN = 60     # 浏览器弹窗限制：1分钟最多弹 1 次

SAFETY_BUFFER = 0.01      # 安全边际(1%)：预留给滑点和买卖价差的扣损空间
# ==========================================

last_tg_time = 0
last_browser_time = 0

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Telegram 发送失败: {e}")

def send_telegram_safe(msg):
    global last_tg_time
    now = time.time()
    time_since_last = now - last_tg_time
    if time_since_last < TG_RATE_LIMIT:
        time.sleep(TG_RATE_LIMIT - time_since_last)
    send_telegram_message(msg)
    last_tg_time = time.time()

def open_browser_safe(url):
    global last_browser_time
    now = time.time()
    if now - last_browser_time < BROWSER_COOLDOWN:
        return
    try:
        webbrowser.open(url)
        last_browser_time = time.time()
    except Exception as e:
        print(f"无法打开浏览器: {e}")

def should_notify(market_id, total_price, notified_markets):
    if not market_id: return False
    now = time.time()
    if market_id in notified_markets:
        last = notified_markets[market_id]
        if now - last["time"] < COOLDOWN:
            if abs(total_price - last["price"]) < PRICE_DELTA:
                return False
    notified_markets[market_id] = {"time": now, "price": total_price}
    return True

def check_polymarket(notified_markets):
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": 100, "active": "true", "closed": "false"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        markets = data.get("data", data) if isinstance(data, dict) else data
            
        for market in markets:
            if not isinstance(market, dict): continue
            
            # ======== 1. 市场类型过滤 ========
            question = market.get("question", "Unknown Market")
            question_lower = question.lower()
            if any(x in question_lower for x in ["election", "president", "2028"]):
                continue
                
            outcomes = market.get("outcomes", [])
            prices = market.get("outcomePrices", [])
            liquidity = float(market.get("liquidity", 0))
            
            # 过滤死水池
            if liquidity <= 1000: continue
                
            if len(outcomes) >= 2 and len(prices) >= 2:
                try:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                except (ValueError, TypeError):
                    continue
                
                # ======== 2. 盘口极端价格过滤 ======== 
                if yes_price < 0.05 or yes_price > 0.95 or no_price < 0.05 or no_price > 0.95:
                    continue
                
                total_price = yes_price + no_price
                
                if 0 < total_price < 1.0:
                    fee = total_price * 0.02
                    total_cost = total_price + fee
                    
                    abs_profit = 1.0 - total_cost
                    profit_ratio = abs_profit / total_cost
                    
                    # ======== 3. 安全边际 (扣除滑点后的真实利润) ========
                    real_profit = profit_ratio - SAFETY_BUFFER
                    
                    # 只有在扣除 1% 滑点损失后，依然大于 2% 才值得抢
                    if real_profit > 0.02:
                        market_id = market.get("id")
                        market_url = f"https://polymarket.com/market/{market_id}"
                        
                        if not should_notify(market_id, total_price, notified_markets):
                            continue
                            
                        # 分级判定
                        if real_profit > 0.04:
                            tag = "🔥 高级套利"
                            open_browser = True
                        else:
                            tag = "🟢 普通套利"
                            open_browser = False
                            
                        msg = f"""{tag}
                        
📊 市场: {question}
💰 理论利润: {round(profit_ratio * 100, 2)}%
🛡️ 实盘净利: {round(real_profit * 100, 2)}%
💧 流动性: ${liquidity:,.2f}

👉 {market_url}"""

                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n{msg}\n")
                        send_telegram_safe(msg)
                        
                        if open_browser:
                            open_browser_safe(market_url)
                            
    except requests.RequestException as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] API 请求异常: {e}")

def main():
    if not TELEGRAM_TOKEN or "填入" in TELEGRAM_CHAT_ID:
        print("⚠️ 警告: 未正确配置 Telegram (请检查 CHAT_ID)，将在纯控制台模式下运行。\n")
    else:
        print("✅ Telegram 机器人已就绪。\n")
        
    print("🚀 ========== Polymarket 旗舰防损套利扫描器已启动 ==========\n")
    print("正在扫盘...如果 Telegram 就绪，请等待真实猎物出现。\n")
    
    notified_markets = {}
    
    while True:
        try:
            check_polymarket(notified_markets)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控异常捕获: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
