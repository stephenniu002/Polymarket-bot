import os
import json
import csv
import requests
from datetime import datetime
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.clob_client import ClobClient
from telegram import Bot
from dotenv import load_dotenv

# 载入环境变量
load_dotenv()

RELAYER_API_KEY = os.getenv("RELAYER_API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Telegram Bot 初始化
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Gamma API URL
MARKETS_URL = "https://gamma-api.polymarket.com/markets"

# ClobClient 初始化
client = ClobClient(relayer_api_key=
