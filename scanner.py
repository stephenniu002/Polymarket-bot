import os
import asyncio
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# 1. 加载环境变量 (Railway 环境变量会自动注入)
load_dotenv()

def get_client():
    """初始化并认证 CLOB 客户端"""
    # 必须包含：私钥、Key、Secret、Passphrase
    host = "https://clob.polymarket.com"
    key = os.getenv("WALLET_PRIVATE_KEY")
    chain_id = POLYGON

    client = ClobClient(host, key=key, chain_id=chain_id)
    
    # 核心：设置 API 凭证（通过你之前导出的 creds）
    creds = {
        "key": os.getenv("POLY_API_KEY"),
        "secret": os.getenv("POLY_API_SECRET"),
        "passphrase": os.getenv("POLY_API_PASSPHRASE")
    }
    client.set_api_creds(creds)
    return client

# 2. 下单逻辑 (使用 SDK 替代 requests)
def place_market_order(client, token_id, side, size, price):
    try:
        # 创建订单对象 (SDK 会处理 EIP-712 签名)
        order_args = {
            "price": price,
            "size": size,
            "side": side.upper(), # "BUY" 或 "SELL"
            "token_id": token_id
        }
        # 1. 创建订单内容
        signed_order = client.create_order(order_args)
        # 2. 真正发送到 Polymarket 服务器
        resp = client.post_order(signed_order)
        return resp
    except Exception as e:
        print(f"❌ 下单失败: {e}")
        return None

async def main():
    # 初始化客户端
    client = get_client()
    print("✅ 身份认证成功，机器人启动中...")

    # 这里建议参考视频中的订阅模式，或者保持你之前的逻辑
    # 示例：监控价格并下单
    # resp = place_market_order(client, "TOKEN_ID_HERE", "BUY", 100, 0.50)
    # print(resp)

if __name__ == "__main__":
    asyncio.run(main())
