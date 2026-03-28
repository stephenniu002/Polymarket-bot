import os
import time
import requests
from datetime import datetime

# 尝试从环境变量获取 Telegram 配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text):
    """发送 Telegram 消息通知"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    
    try:
        # 3. 增强异常处理 - 发送 TG 消息时也可能抛出异常
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Telegram 发送失败: {e}")

def check_polymarket(notified_markets):
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": 100, "active": "true", "closed": "false"}
    
    try:
        # 3. 增强异常处理 - API 请求失败
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 兼容列表直接返回或包裹在 data 字典中的情况
        markets = data.get("data", data) if isinstance(data, dict) else data
            
        for market in markets:
            if not isinstance(market, dict):
                continue
                
            market_id = market.get("id")
            question = market.get("question", "Unknown Market")
            outcomes = market.get("outcomes", [])
            prices = market.get("outcomePrices", [])
            liquidity = float(market.get("liquidity", 0))
            
            # 2. 增加流动性过滤（>1000）
            if liquidity <= 1000:
                continue
                
            # 确保是二元市场且含有价格数据
            if len(outcomes) >= 2 and len(prices) >= 2:
                try:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                except (ValueError, TypeError):
                    continue
                
                total_price = yes_price + no_price
                
                if 0 < total_price < 1.0:
                    fee = total_price * 0.02
                    total_cost = total_price + fee
                    
                    profit = 1.0 - total_cost
                    profit_pct = (profit / total_cost) * 100
                    
                    if profit_pct > 2.0:
                        # 1. 避免重复提醒，如果已经通知过则跳过
                        if market_id in notified_markets:
                            continue
                            
                        # 记录到已通知列表
                        notified_markets.add(market_id)
                        
                        # 构造消息
                        msg = (
                            f"🚨 <b>发现套利机会!</b>\n\n"
                            f"<b>市场:</b> {question}\n"
                            f"<b>流动性:</b> ${liquidity:,.2f}\n"
                            f"<b>价格:</b> Yes={yes_price}, No={no_price}\n"
                            f"<b>总价:</b> {total_price:.4f} (含2%手续费: {total_cost:.4f})\n"
                            f"<b>利润率:</b> {profit_pct:.2f}% (净利润: {profit:.4f} USDC)"
                        )
                        
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n{msg}\n")
                        send_telegram_message(msg)
                        
    except requests.RequestException as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] API 请求异常: {e}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 处理数据时发生未知错误: {e}")

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未检测到 TELEGRAM_TOKEN 或 TELEGRAM_CHAT_ID 环境变量，Telegram 通知已禁用。\n")
    else:
        print("✅ Telegram 通知已启用。\n")
        
    print("开始监控 Polymarket，每 5 秒请求一次...\n")
    
    # 使用集合维护已经通知过的市场 ID 列表
    notified_markets = set()
    
    while True:
        check_polymarket(notified_markets)
        time.sleep(5)

if __name__ == "__main__":
    main()
