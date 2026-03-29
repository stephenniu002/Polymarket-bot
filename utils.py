import os
import requests
import logging

logger = logging.getLogger("PolyUtils")

def send_telegram_msg(message: str):
    """发送 Telegram 消息"""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.warning("⚠️ TG 配置缺失，跳过发送")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ TG 发送异常: {e}")
        return False

def calculate_kelly(win_rate, odds, bankroll):
    """凯利公式仓位计算"""
    if odds <= 0: return 0
    q = 1 - win_rate
    f = (win_rate * odds - q) / odds
    # 采用 1/4 凯利
    suggested_amount = (bankroll * f) / 4
    return max(0, round(suggested_amount, 2))
