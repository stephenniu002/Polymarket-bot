try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logger.info(f"Telegram 已发送 {len(opportunities)} 个机会")
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")


def main():
    logger.info("=== Polymarket 套利监控机器人启动 ===")
    
    while True:
        try:
            opportunities = detect_arbitrage(min_profit_pct=0.8)

            if opportunities:
                logger.info(f"发现 {len(opportunities)} 个套利机会！")
                save_to_csv(opportunities)
                send_telegram(opportunities)
            else:
                logger.info("本次未发现符合条件的套利机会")

        except Exception as e:
            logger.error(f"主循环发生错误: {e}")

        time.sleep(30)  # 每30秒扫描一次


if name == "main":
    main()
