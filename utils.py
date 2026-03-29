import os, requests, logging
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

def get_trading_client():
    pk, addr = os.getenv("POLY_PRIVATE_KEY"), os.getenv("POLY_ADDRESS")
    if not (pk and addr): return None
    try:
        client = ClobClient(host="https://clob.polymarket.com", key=pk, chain_id=POLYGON)
        client.set_api_creds(client.create_or_derive_api_key())
        return client
    except: return None

def get_poly_price(token_id):
    try:
        res = requests.get(f"https://clob.polymarket.com/book?token_id={token_id}", timeout=5).json()
        bid = float(res['bids'][0]['price']) if res.get('bids') else 0.0
        ask = float(res['asks'][0]['price']) if res.get('asks') else 1.0
        return bid, ask
    except: return None, None

def send_telegram_msg(message):
    token, chat_id = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                   json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=5)
