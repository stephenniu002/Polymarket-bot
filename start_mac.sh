#!/bin/bash

echo "======================================================="
echo "龙虾火控系统 v2 - Polymarket 自动下单机器人 (Mac/Linux版)"
echo "======================================================="
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.10 或以上版本。"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[1/3] 正在创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "[2/3] 正在安装依赖包..."
pip install -r requirements.txt
playwright install chromium

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "[警告] 未找到 .env 配置文件，正在从模板复制..."
    cp .env.example .env
    echo "请打开 .env 文件，填入您的 Telegram Token 和 Chat ID。"
    read -p "填写完成后，按回车键继续..."
fi

# 启动机器人
echo "[3/3] 正在启动机器人..."
echo ""
python playwright_trader.py
