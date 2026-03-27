import time

def main():
    while True:
        try:
            print(f"[{datetime.now()}] 开始扫描市场...")
            markets = fetch_markets()
            opportunities = detect_arbitrage(markets)
            
            if opportunities:
                print(f"发现 {len(opportunities)} 个套利机会！")
                save_csv(opportunities)
                send_telegram(opportunities)
                for opp in opportunities:
                    place_order(opp)
            else:
                print("暂无套利机会")
                
        except Exception as e:
            print(f"运行出错: {e}")
        
        print("等待 60 秒后下一次扫描...\n")
        time.sleep(60)   # 每 60 秒扫描一次，可自行调整
