@echo off
REM ==========================================
REM DiamondMemory Electron EXE 打包脚本
REM ==========================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set FRONTEND_DIR=%PROJECT_DIR%\frontend

echo 🚀 开始打包 DiamondMemory (Electron + Vue3) for Windows...

REM 1. 下载 Ollama 二进制
echo 📦 0/4 正在准备 Ollama 二进制...
cd /d "%PROJECT_DIR%"
call scripts\download-ollama-win.bat
if errorlevel 1 (
    echo ⚠️ Ollama 下载失败，继续打包（用户需自行安装 Ollama）
)

REM 2. 编译后端二进制 (Nuitka)
echo 🔨 1/4 正在编译 Python 后端 (Nuitka)...
cd /d "%PROJECT_DIR%"
call scripts\build-backend.bat
if errorlevel 1 (
    echo ❌ 后端编译失败！
    exit /b 1
)

REM 3. 安装前端依赖并打包
echo 🔨 2/4 正在编译前端代码并打包 Electron 应用...
cd /d "%FRONTEND_DIR%"
call npm install
if errorlevel 1 (
    echo ❌ 前端依赖安装失败！
    exit /b 1
)

call npm run electron:build:win
if errorlevel 1 (
    echo ❌ Electron 打包失败！
    exit /b 1
)

REM 4. 复制生成的 EXE 到桌面
echo 📦 3/4 正在将 EXE 复制到桌面...
for /f "delims=" %%i in ('dir /b /s "%FRONTEND_DIR%\dist\electron\*.exe"') do (
    REM 可选：在 CI/干净机环境执行“装完即用”冒烟测试（安装→启动→health→创建/检索→退出）
    REM 启用方式：set RUN_SMOKE_TEST=1 && DM开发辅助\create_exe.bat
    if "%RUN_SMOKE_TEST%"=="1" (
        echo 🧪 3.5/4 RUN_SMOKE_TEST=1，开始执行 NSIS 冒烟测试...
        powershell -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\smoke\smoke_win_nsis.ps1" -InstallerPath "%%i" -TimeoutSec 180
        if errorlevel 1 (
            echo ❌ 冒烟测试失败！
            exit /b 1
        )
        echo ✅ NSIS 冒烟测试通过
    )

    copy "%%i" "%USERPROFILE%\Desktop\"
    echo ✅ 打包完成！EXE 文件已保存到桌面: %USERPROFILE%\%%~nxi
    goto :done
)

:done
echo.
echo 📋 打包内容说明：
echo   ✅ Electron 前端 (Vue3 + TypeScript)
echo   ✅ Python 后端 (Nuitka 编译，无需安装 Python)
echo   ✅ Ollama 推理引擎 (内嵌，无需单独安装)
echo   ⚠️  大模型权重需在软件内手动下载
echo.
echo 🔄 使用流程：
echo   1. 安装后启动软件
echo   2. 进入「模型管理」页面
echo   3. 点击下载推荐模型 (qwen3.5:4b + bge-m3)
echo   4. 下载完成后重启软件，模型自动常驻内存
echo   5. 或配置外部 API，保存后自动连接
pause
