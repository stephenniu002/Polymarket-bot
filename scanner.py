def main():
    if not TELEGRAM_TOKEN or "填入" in TELEGRAM_CHAT_ID:
        print("⚠️ 警告: 未正确配置 Telegram (请检查 CHAT_ID)，将在纯控制台模式下运行。\n")
    else:
        print("✅ Telegram 机器人已就绪。\n")
        
        # 👇 就是加了这一行！启动成功后会立刻给你的手机发一条电报消息
        send_telegram_safe("✅ <b>监控机器人启动成功！</b>\n\n网络通畅，API 正常。\n正在为您 24 小时死盯 Polymarket 套利机会... 🚀")
        
    print("🚀 ========== Polymarket 旗舰防损套利扫描器已启动 ==========\n")
    print("正在扫盘...如果 Telegram 就绪，请等待真实猎物出现。\n")
    
    notified_markets = {}
    
    while True:
        try:
            check_polymarket(notified_markets)
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控异常捕获: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
