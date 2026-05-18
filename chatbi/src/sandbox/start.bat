@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   ChatBI Sandbox - 启动中...
echo ========================================
echo.

REM 检查 .env 配置
if not exist .env (
    echo 正在创建 .env 文件，请填写 API Key...
    copy .env.example .env >nul
    echo ⚠️  请先在 .env 文件中填写你的 LLM_API_KEY！
    echo     打开文件：notepad .env
    pause
    exit /b 1
)

findstr /C:"your-maas-api-key-here" .env >nul 2>&1
if %errorlevel%==0 (
    echo ⚠️  警告：请先在 .env 文件中填写你的 API Key！
    echo     打开文件：notepad .env
    pause
    exit /b 1
)

echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 需要 Python 3.10+，请先安装: https://python.org/downloads
    pause
    exit /b 1
)

echo [2/5] 安装后端依赖...
cd backend
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo ❌ 后端依赖安装失败
    pause
    exit /b 1
)
REM 锁定 httpx 版本（openai 兼容性）
pip install "httpx==0.27.2" -q

echo [3/5] 生成演示数据（首次运行约需30秒）...
if not exist data\retail.duckdb (
    python data\seed.py
)

echo [4/5] 启动后端服务...
start "ChatBI Backend" cmd /k "uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul

cd ..\frontend
echo [5/5] 安装前端依赖并启动...
if not exist node_modules (
    call npm install
)
start "ChatBI Frontend" cmd /k "npm run dev"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo  ✅ ChatBI Sandbox 已启动！
echo.
echo     前端: http://localhost:5173
echo     后端 API: http://localhost:8000/docs
echo ========================================
echo.
start http://localhost:5173
pause
