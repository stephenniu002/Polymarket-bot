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

    # RPC (Alchemy or QuickNode recommended for low latency)
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

    # Telegram report interval (seconds). Default 1800 = 30 minutes
    REPORT_INTERVAL = int(os.getenv("REPORT_INTERVAL", "1800"))

    # 7 Target Coins (confirmed active on Polymarket 5M page as of May 2026)
    # Slug format: {coin}-updown-5m-{unix_timestamp_rounded_to_300}
    # ADA is NOT available; replaced with BNB (confirmed active)
    TARGET_COINS = ["btc", "eth", "sol", "doge", "xrp", "bnb", "hype"]

    # HYPE specific settings (higher volatility = higher slippage tolerance)
    HYPE_SLIPPAGE_TOLERANCE = float(os.getenv("HYPE_SLIPPAGE_TOLERANCE", "0.005"))

    # Arbitrage threshold: YES + NO ask price must be below this to trigger
    # Real-world observation: market usually prices at ~0.99+0.99=1.98 (no arb)
    # Arb windows appear briefly at market open or during high volatility
    ARB_THRESHOLD = float(os.getenv("ARB_THRESHOLD", "0.98"))

config = Config()
