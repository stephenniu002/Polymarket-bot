import time
import requests
from datetime import datetime

def check_polymarket():
    url = "https://gamma-api.polymarket.com/markets"
    # 获取一定数量的活跃市场
    params = {"limit": 100, "active": "true", "closed": "false"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        markets = response.json()
        
        if isinstance(markets, dict) and "data" in markets:
            markets = markets["data"]
            
        for market in markets:
            outcomes = market.get("outcomes", [])
            prices = market.get("outcomePrices", [])
            
            # 确保是二元市场且含有价格数据
            if len(outcomes) >= 2 and len(prices) >= 2:
                try:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                except (ValueError, TypeError):
                    continue
                
                total_price = yes_price + no_price
                
                if 0 < total_price < 1.0:
                    # 按照用户要求：扣除2%手续费
                    fee = total_price * 0.02
                    total_cost = total_price + fee
                    
                    # 利润计算 (成功后获得 1 USDC)
                    profit = 1.0 - total_cost
                    profit_pct = (profit / total_cost) * 100
                    
                    if profit_pct > 2.0:
                        question = market.get("question", "Unknown Market")
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发现机会!")
                        print(f"市场: {question}")
                        print(f"价格: Yes={yes_price}, No={no_price}")
                        print(f"Yes+No: {total_price:.4f} (加上2%手续费总成本: {total_cost:.4f})")
                        print(f"预计利润率: {profit_pct:.2f}% (净利润: {profit:.4f})\n")
                        
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 请求异常: {e}")

def main():
    print("开始监控 Polymarket，每 5 秒请求一次...\n")
    while True:
        check_polymarket()
        time.sleep(5)

if __name__ == "__main__":
    main()
