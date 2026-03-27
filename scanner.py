import os
import requests
import pandas as pd
from datetime import datetime
import time
import logging

from py_clob_client.clob_types import OrderArgs, OrderType, Side
from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("请在 .env 文件中设置 RELAYER_API_KEY, WALLET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")

# 初始化客户端
bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = ClobClient(
    host="https://clob.polymarket.com",
    relayer_api_key=RELAYER_API_KEY,
    private_key=WALLET_PRIVATE_KEY
)

# Gamma API（获取市场列表）
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets?closed=false&limit=200"

def fetch_active_markets():
    """获取活跃市场列表"""
    try:
        resp =
