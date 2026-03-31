# --- 增加实盘连接逻辑 ---
from polymarket_client import PolymarketClient # 假设你的库名
import os

# 从 Railway 变量读取私钥
POLY_CLIENT = PolymarketClient(
    api_key=os.getenv("POLY_API_KEY"),
    private_key=os.getenv("WALLET_PRIVATE_KEY")
)

async def check_and_bet(price, current_roi):
    """
    V3 核心：只有满足以下三个条件，才真金白银下注
    """
    # 1. 模拟 ROI 必须稳定在 1.1 以上（留出滑点空间）
    if current_roi < 1.1:
        print("⚠️ 模拟 ROI 不足，放弃实盘下单")
        return

    # 2. 检查 Polymarket 订单簿（防滑点）
    # 获取 $0.01 - $0.03 区间的深度
    orderbook = await POLY_CLIENT.get_orderbook("ETH-PRICE-REVERSAL-MARKET")
    available_depth = orderbook.get_depth(price_limit=0.03)
    
    if available_depth < 10: # 如果连 10 刀的深度都没有，就不进场
        print("❌ 深度不足，实盘滑点过大，取消")
        return

    # 3. 满足条件，执行实盘
    print(f"🚀 [REAL TRADE] 条件达成！下单 $10 @ {price}")
    try:
        await POLY_CLIENT.place_order(amount=10, side="buy", price=0.02)
    except Exception as e:
        print(f"❌ 下单失败: {e}")

# --- 修改后的主循环片段 ---
if strategy.check_signal():
    # ... 原有的模拟逻辑 ...
    # 增加实盘判定
    await check_and_bet(price, s['roi'])
