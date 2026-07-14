@echo off
chcp 65001 >nul
title Multi-source Artist Grabber
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
    python --version >nul 2>nul
    if errorlevel 1 set "PY_CMD=py -3"
)

%PY_CMD% --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 Python 3。请先安装：https://www.python.org/downloads/
    echo 安装时请勾选 Add Python to PATH。
    echo.
    pause
    exit /b 1
)

%PY_CMD% -c "import gallery_dl, websocket" >nul 2>nul
if errorlevel 1 (
    echo [准备] 正在安装基础抓取依赖 gallery-dl / websocket-client ...
    %PY_CMD% -m pip install --disable-pip-version-check --upgrade -r requirements.txt
    if errorlevel 1 (
        echo [警告] 基础依赖安装失败。建议运行根目录的 install_dependencies.bat。
    )
)

%PY_CMD% -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8710/api/sources',timeout=1)); assert isinstance(d.get('sources'),list)" >nul 2>nul
if not errorlevel 1 (
    echo [提示] 服务已经在 http://127.0.0.1:8710/ 运行，正在打开页面 ...
    start "" "http://127.0.0.1:8710/"
    exit /b 0
)

echo.
echo 正在启动 Multi-source Artist Grabber ...
echo 关闭本窗口即可退出服务。
echo.
%PY_CMD% app.py
pause
