import os, requests

def get_poly_price(token_id):
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        res = requests.get(url, timeout=5).json()
        bid = float(res['bids'][0]['price']) if res.get('bids') else 0.0
        ask = float(res['asks'][0]['price']) if res.get('asks') else 1.0
        return bid, ask
    except: return None, None

def send_telegram_msg(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                       json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def calculate_kelly_bet(win_rate, price, bankroll=1260):
    odds = (1 - price) / price
    f = (win_rate * odds - (1 - win_rate)) / odds
    return max(0, round((bankroll * f) / 4, 2))
