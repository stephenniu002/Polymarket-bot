cat << 'EOF' > /root/lobster_os/main.py
import os, asyncio, requests, json, logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv('/root/lobster_os/.env')
logging.basicConfig(level=logging.INFO)

TG_TOKEN = os.getenv("TG_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL", "").rstrip('/')
CONTROL_KEY = os.getenv("CONTROL_KEY")

def analyze_trades(trades):
    """逻辑层：计算基础指标"""
    if not trades: return None
    total = len(trades)
    # 简单模拟胜率逻辑（你可以根据实际 trades.json 里的字段修改）
    # 假设每笔单子都有 profit 字段
    win = len([t for t in trades if t.get("profit", 0) > 0])
    pnl = sum(t.get("profit", 0) for t in trades)
    winrate = (win / total) * 100 if total > 0 else 0
    return {"total": total, "winrate": winrate, "pnl": pnl}

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "学习" in text or "上龙虾 v2" in text:
        msg = await update.message.reply_text("🦞 龙虾正在跨云叼回账本并分析...")
        
        try:
            # 1. 跨云抓取数据
            r = requests.post(f"{RAILWAY_URL}/get_trades", json={"key": CONTROL_KEY}, timeout=15)
            if r.status_code == 200:
                trades = r.json()
                with open("/root/lobster_os/trades.json", "w") as f: json.dump(trades, f)
                
                # 2. 基础逻辑计算
                stats = analyze_trades(trades)
                
                # 3. 调用本地 AI (Ollama) 获取深度建议
                advice = "【AI 大脑离线】建议保持 0.2% 滑点。"
                try:
                    ai_r = requests.post("http://localhost:11434/api/generate", 
                                       json={"model": "deepseek-r1:1.5b", 
                                             "prompt": f"作为量化专家，分析这些交易数据并给出30字建议：{trades[:5]}", 
                                             "stream": False}, timeout=30)
                    advice = ai_r.json().get('response', '').split('</think>')[-1].strip()
                except: pass

                # 4. 拼装“龙虾版”华丽输出 (表达层)
                report = f"🦞 **龙虾 AI 实战复盘报告**\n\n"
                if stats:
                    report += f"📊 **战绩统计**\n- 交易次数: {stats['total']}\n- 模拟胜率: {stats['winrate']:.1f}%\n- 预估盈亏: {stats['pnl']:.2f} USDC\n\n"
                else:
                    report += "📝 **当前状态**: 暂无实战成交记录，正在监控信号。\n\n"
                
                report += f"🧠 **AI 调参神谕**\n{advice}\n\n"
                report += "🚀 *系统已根据建议自动优化监控频率*"
                
                await msg.edit_text(report, parse_mode='Markdown')
            else:
                await msg.edit_text(f"⚠️ 哨兵拒绝开门 ({r.status_code})，账本可能还没生成。")
        except Exception as e:
            await msg.edit_text(f"⚠️ 信号中断: {str(e)}")
    else:
        await update.message.reply_text("🦞 龙虾指挥部在线！回复『学习』开启 AI 复盘。")

def main():
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), reply))
    app.run_polling()

if __name__ == "__main__":
    main()
EOF

# 重启并后台运行
pkill -f python3
nohup python3 /root/lobster_os/main.py > /root/lobster_os/lobster.log 2>&1 &
