import os, requests, logging

logger = logging.getLogger("PolyUtils")

def get_poly_price(token_id):
    """从 Polymarket CLOB 获取实时买卖盘"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        res = requests.get(url, timeout=5).json()
        bid = float(res['bids'][0]['price']) if res.get('bids') else 0.0
        ask = float(res['asks'][0]['price']) if res.get('asks') else 1.0
        return bid, ask
    except:
        return None, None

def send_telegram_msg(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    except:
        pass

def calculate_kelly_bet(win_rate, price, bankroll=1260):
    """计算凯利建议仓位"""
    odds = (1 - price) / price
    q = 1 - win_rate
    f = (win_rate * odds - q) / odds
    return max(0, round((bankroll * f) / 4, 2))
