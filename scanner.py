import os
import time
import requests
import webbrowser
from datetime import datetime

# ================= 核心配置区域 =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COOLDOWN = 600            # 市场冷却时间：10分钟 (秒)
PRICE_DELTA = 0.01        # 特殊触发阈值：如果总价变动超过 1%，无视冷却时间强制提醒
TG_RATE_LIMIT = 1         # Telegram 限速：每秒最多发 1 条（防封锁）
BROWSER_COOLDOWN = 60     # 浏览器弹窗限制：1分钟最多开 1 次网页（防卡死）
# ==========================================

# 全局状态变量（用于频率控制）
last_tg_time = 0
last_browser_time = 0

def send_telegram_message(text):
    """底层 Telegram 请求"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Telegram 发送失败: {e}")

def send_telegram_safe(msg):
    """带限速的安全版 Telegram 发送"""
    global last_tg_time
    now = time.time()
    
    # 距离上次发送不足 TG_RATE_LIMIT 秒，阻塞等待保护
    time_since_last = now - last_tg_time
    if time_since_last < TG_RATE_LIMIT:
        time.sleep(TG_RATE_LIMIT - time_since_last)
        
    send_telegram_message(msg)
    last_tg_time = time.time()

def open_browser_safe(url):
    """带冷却控制的安全版浏览器打开"""
    global last_browser_time
    now = time.time()
    
    # 如果还在浏览器弹窗全局冷却期内，直接忽略（防止连弹10个网页）
    if now - last_browser_time < BROWSER_COOLDOWN:
        return
        
    try:
        webbrowser.open(url)
        last_browser_time = time.time()  # 更新最近打开时间
    except Exception as e:
        print(f"无法打开浏览器: {e}")

def should_notify(market_id, total_price, notified_markets):
    """
    智能去重与再次提醒逻辑：
    1. 第一次发现：记录并提醒
    2. 冷却期内 + 价格变化极小：忽略
    3. 冷却期内，但由于砸盘导致套利空间（总价格）突变 (变化 > 1%)：再次提醒！
    4. 超过10分钟冷却期复现机会：提醒
    """
    if not market_id:
        return False
        
    now = time.time()
    
    if market_id in notified_markets:
        last = notified_markets[market_id]
        
        # 如果还在 10 分钟冷却期内
        if now - last["time"] < COOLDOWN:
            # 只有价格变化大于设定的阈值 (默认1%)，才破除冷却期限制
            if abs(total_price - last["price"]) < PRICE_DELTA:
                return False
                
    # 更新内存中的记录 (覆盖时间戳和最新触发价格)
    notified_markets[market_id] = {
        "time": now,
        "price": total_price
    }
    
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
            if not isinstance(market, dict):
                continue
                
            outcomes = market.get("outcomes", [])
            prices = market.get("outcomePrices", [])
            liquidity = float(market.get("liquidity", 0))
            
            # 过滤死水池：流通性太低根本卖不掉
            if liquidity <= 1000:
                continue
                
            if len(outcomes) >= 2 and len(prices) >= 2:
                try:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                except (ValueError, TypeError):
                    continue
                
                total_price = yes_price + no_price
                
                # 总价小于 1 才有讨论套利意义
                if 0 < total_price < 1.0:
                    fee = total_price * 0.02
                    total_cost = total_price + fee
                    
                    abs_profit = 1.0 - total_cost
                    profit_ratio = abs_profit / total_cost
                    
                    if profit_ratio > 0.02:
                        market_id = market.get("id")
                        market_url = f"https://polymarket.com/market/{market_id}"
                        
                        # ======== 新增智能过滤机制 ========
                        if not should_notify(market_id, total_price, notified_markets):
                            continue
                            
                        # 分级判定
                        if profit_ratio > 0.04:
                            tag = "🔥 高级套利"
                            open_browser = True
                        else:
                            tag = "🟢 普通套利"
                            open_browser = False
                            
                        # 格式化推文
                        msg = f"""{tag}
                        
📊 市场: {market.get("question", "Unknown Market")}
💰 利润: {round(profit_ratio * 100, 2)}%
💧 流动性: ${liquidity:,.2f}

👉 {market_url}"""

                        # 终端打印
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n{msg}\n")
                        
                        # ======== 频率安全的执行层 ========
                        send_telegram_safe(msg)
                        
                        if open_browser:
                            open_browser_safe(market_url)
                            
    except requests.RequestException as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] API 网络异常: {e}")

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 警告: 未找到 Telegram 配置，将在纯本地模式下运行。\n")
    else:
        print("✅ Telegram 机器人推送准备就绪。\n")
        
    print("🚀 ========== Polymarket 智能监控系统已开启 ==========\n")
    
    # 结构: { market_id: { "time": ts, "price": total_price } }
    notified_markets = {}
    
    while True:
        try:
            check_polymarket(notified_markets)
        except Exception as e:
            # 捕获异常，确保无论解析遇到什么破损数据，脚手架都不会崩溃退出
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控循环遇到未捕获异常: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    main()
