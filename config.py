import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Polymarket API
    POLY_API_KEY = os.getenv("POLY_API_KEY")
    POLY_API_SECRET = os.getenv("POLY_API_SECRET")
    POLY_API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE")
    WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
    WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

    # RPC
    RPC_URL = os.getenv("RPC_URL", "https://polygon-rpc.com")

    # Telegram
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Bot Settings
    DRY_RUN = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "t")
    MIN_PROFIT_USD = float(os.getenv("MIN_PROFIT_USD", "1.0"))
    MAX_PRICE_IMPACT = float(os.getenv("MAX_PRICE_IMPACT", "0.002"))
    MAX_GAS_FEE_RATIO = float(os.getenv("MAX_GAS_FEE_RATIO", "0.2"))
    TRADE_AMOUNT_USD = float(os.getenv("TRADE_AMOUNT_USD", "10.0"))

    # Target Markets (7 coins, 5m)
    # These are example condition IDs, need to be updated with actual ones
    TARGET_MARKETS = [
        "BTC-5M",
        "ETH-5M",
        "SOL-5M",
        "DOGE-5M",
        "XRP-5M",
        "ADA-5M",
        "HYPE-5M"
    ]
    
    # HYPE specific settings
    HYPE_SLIPPAGE_TOLERANCE = 0.005 # 0.5% for high volatility

config = Config()
