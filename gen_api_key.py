"""
从私钥派生 Polymarket CLOB API 凭证
"""
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

pk = os.getenv('WALLET_PRIVATE_KEY').replace('0x', '')
HOST = 'https://clob.polymarket.com'

print("正在连接 Polymarket CLOB...")
client = ClobClient(HOST, key=pk, chain_id=POLYGON)

try:
    # 派生 API 凭证（从私钥签名生成，无需网站操作）
    creds = client.create_or_derive_api_creds()
    print("\n✅ CLOB API 凭证生成成功！")
    print(f"POLY_API_KEY={creds.api_key}")
    print(f"POLY_API_SECRET={creds.api_secret}")
    print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
    
    # 写入 .env 文件
    env_path = '.env'
    with open(env_path, 'r') as f:
        content = f.read()
    
    content = content.replace(
        f"POLY_API_KEY={os.getenv('POLY_API_KEY')}",
        f"POLY_API_KEY={creds.api_key}"
    )
    content = content.replace(
        f"POLY_API_SECRET={os.getenv('POLY_API_SECRET')}",
        f"POLY_API_SECRET={creds.api_secret}"
    )
    content = content.replace(
        f"POLY_API_PASSPHRASE={os.getenv('POLY_API_PASSPHRASE')}",
        f"POLY_API_PASSPHRASE={creds.api_passphrase}"
    )
    
    with open(env_path, 'w') as f:
        f.write(content)
    
    print("\n✅ .env 文件已自动更新！")
    
    # 验证连接
    client.set_api_creds(creds)
    orders = client.get_orders()
    print(f"✅ API 验证成功！当前挂单数: {len(orders) if orders else 0}")
    
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
