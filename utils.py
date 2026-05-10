import httpx
from loguru import logger
from config import config

async def send_telegram_message(message: str):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set, skipping notification.")
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def format_report(stats: dict) -> str:
    return f"""📊 【龙虾火控系统 - 半小时战报】
━━━━━━━━━━━━━━━━━━━━━
⏰ 时间: {stats['time']}
💰 当前总余额: ${stats['balance']:.2f} (USDC)
📈 周期净损益: {stats['pnl']:+.2f} (过去30min)
⛽ 累计Gas消耗: ${stats['gas_cost']:.2f}
🎯 交易成功率: {stats['win_rate']:.0f}% ({stats['wins']}/{stats['total_trades']} 获利)
🛡️ 熔断状态: {stats['status']}
🚀 活跃市场: {', '.join(stats['active_markets'])}
━━━━━━━━━━━━━━━━━━━━━
备注: {stats['remark']}"""
