@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Artist Source Grabber - 依赖安装
cd /d "%~dp0"

if /i "%~1"=="--dry-run" goto dry_run

echo.
echo ============================================================
echo   Artist Source Grabber - 一键安装全部依赖
echo ============================================================
echo.

set "PY_BOOT="
call :find_python
if defined PY_BOOT goto python_ready

echo [1/6] 未检测到 64 位 Python 3.11 或更高版本。
where winget >nul 2>nul
if errorlevel 1 (
    echo [错误] 当前系统没有 winget，无法自动安装 Python。
    echo 请从 https://www.python.org/downloads/ 安装 Python 3.12，
    echo 安装时勾选 Add Python to PATH，然后重新运行本脚本。
    goto failed
)

echo [1/6] 正在通过 winget 安装 64 位 Python 3.12 ...
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements --silent
if errorlevel 1 (
    echo [错误] Python 自动安装失败，请检查网络或手动安装 Python 3.12。
    goto failed
)

call :find_python
if not defined PY_BOOT (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%~fD\python.exe" set "PY_BOOT=%%~fD\python.exe"
)
if not defined PY_BOOT (
    echo [提示] Python 已安装，但当前窗口尚未刷新环境变量。
    echo 请关闭本窗口并再次双击 install_dependencies.bat。
    goto failed
)

:python_ready
echo [1/6] Python: !PY_BOOT!
"!PY_BOOT!" -c "import sys,struct; print('       版本:', sys.version.split()[0], '/', struct.calcsize('P')*8, 'bit')"

echo.
echo [2/6] 正在创建项目独立环境 .venv ...
if not exist ".venv\Scripts\python.exe" (
    "!PY_BOOT!" -m venv ".venv"
    if errorlevel 1 (
        echo [错误] 无法创建 .venv，请确认 Python 安装完整。
        goto failed
    )
) else (
    echo        已存在，继续更新。
)
set "PY=.venv\Scripts\python.exe"

echo.
echo [3/6] 正在更新 pip / setuptools / wheel ...
"%PY%" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 goto pip_failed

echo.
echo [4/6] 正在安装抓图、登录和本地 ONNX 打标依赖 ...
echo        首次安装 onnxruntime / numpy 可能需要几分钟。
"%PY%" -m pip install --disable-pip-version-check --upgrade -r requirements-all.txt
if errorlevel 1 goto pip_failed

echo.
echo [5/6] 正在检查 Microsoft Visual C++ x64 运行库 ...
where winget >nul 2>nul
if errorlevel 1 (
    echo [警告] 无法自动检查 VC++ 运行库；如 ONNX 报 DLL 错误，请安装：
    echo        https://aka.ms/vs/17/release/vc_redist.x64.exe
) else (
    winget list --id Microsoft.VCRedist.2015+.x64 -e >nul 2>nul
    if errorlevel 1 (
        echo        正在安装 Microsoft Visual C++ 2015-2022 x64 运行库 ...
        winget install --id Microsoft.VCRedist.2015+.x64 -e --source winget --accept-package-agreements --accept-source-agreements --silent
        if errorlevel 1 echo [警告] VC++ 运行库自动安装失败；ONNX 可能无法加载 DLL。
    ) else (
        echo        已安装。
    )
)

echo.
echo [6/6] 正在检查 Google Chrome ...
call :find_chrome
if defined CHROME_EXE (
    echo        已找到: !CHROME_EXE!
) else (
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 Google Chrome。X / Pixiv 专用登录窗口将不可用。
        echo        请手动安装 Chrome: https://www.google.com/chrome/
    ) else (
        echo        正在安装 Google Chrome ...
        winget install --id Google.Chrome -e --source winget --accept-package-agreements --accept-source-agreements --silent
        if errorlevel 1 (
            echo [警告] Chrome 自动安装失败。公共来源仍可使用，但 X / Pixiv 登录需要浏览器。
        ) else (
            call :find_chrome
        )
    )
)
where taskkill.exe >nul 2>nul
if errorlevel 1 echo [警告] 未找到 Windows taskkill.exe，专用浏览器退出兜底不可用。

echo.
echo [验证] 正在验证全部 Python 模块 ...
"%PY%" -c "import gallery_dl, websocket, numpy, onnxruntime; from PIL import Image; print('       gallery-dl:', gallery_dl.__version__); print('       websocket-client:', websocket.__version__); print('       numpy:', numpy.__version__); print('       onnxruntime:', onnxruntime.__version__); print('       Pillow:', Image.__version__)"
if errorlevel 1 goto pip_failed

echo.
echo ============================================================
echo [完成] 所有依赖均已安装到项目目录下的 .venv。
echo        现在可以直接双击 start.bat 启动。
echo ============================================================
echo.
pause
exit /b 0

:find_python
for %%C in (python.exe) do for /f "delims=" %%P in ('where %%C 2^>nul') do if not defined PY_BOOT (
    "%%P" -c "import sys,struct; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_BOOT=%%P"
)
if not defined PY_BOOT (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
        "%%P" -c "import sys,struct; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>nul
        if not errorlevel 1 set "PY_BOOT=%%P"
    )
)
exit /b 0

:find_chrome
set "CHROME_EXE="
for %%P in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do if not defined CHROME_EXE if exist "%%~P" set "CHROME_EXE=%%~P"
exit /b 0

:dry_run
echo [检查模式] 不会安装或修改任何内容。
call :find_python
if defined PY_BOOT (echo Python: !PY_BOOT!) else (echo Python: 未找到符合要求的 64 位 Python 3.11+)
call :find_chrome
if defined CHROME_EXE (echo Chrome: !CHROME_EXE!) else (echo Chrome: 未找到)
where winget >nul 2>nul && (echo winget: 可用) || (echo winget: 不可用)
where taskkill.exe >nul 2>nul && (echo taskkill: 可用) || (echo taskkill: 不可用)
if exist requirements-all.txt (echo requirements-all.txt: 已找到) else (echo requirements-all.txt: 缺失 & exit /b 1)
exit /b 0

:pip_failed
echo.
echo [错误] Python 依赖安装或验证失败。
echo 常见原因：网络代理、杀毒软件拦截、磁盘空间不足。
echo 修复后重新运行本脚本即可，已下载的内容会被复用。
goto failed

:failed
echo.
pause
exit /b 1
