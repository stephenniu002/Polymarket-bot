@echo off
echo =======================================================
echo 龙虾火控系统 v2 - Polymarket 自动下单机器人 (Windows版)
echo =======================================================
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 或以上版本。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b
)

:: 检查虚拟环境
if not exist "venv" (
    echo [1/3] 正在创建 Python 虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境
call venv\Scripts\activate

:: 安装依赖
echo [2/3] 正在安装依赖包...
pip install -r requirements.txt
playwright install chromium

:: 检查 .env 文件
if not exist ".env" (
    echo [警告] 未找到 .env 配置文件，正在从模板复制...
    copy .env.example .env
    echo 请打开 .env 文件，填入您的 Telegram Token 和 Chat ID。
    echo 填写完成后，按任意键继续...
    pause
)

:: 启动机器人
echo [3/3] 正在启动机器人...
echo.
python playwright_trader.py

pause
