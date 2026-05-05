@echo off
REM 钻石记忆系统后端编译脚本 - Windows
REM 使用Nuitka将Python后端编译为机器码

echo Building Python backend (Nuitka)...

REM 切换到项目根目录
cd /d "%~dp0.."

REM 检查Nuitka是否安装
pip show nuitka >nul 2>&1
if errorlevel 1 (
    echo Installing Nuitka...
    pip install nuitka
)

REM 清理旧输出
echo Cleaning old build artifacts...
rmdir /s /q dist\backend

REM 编译后端
echo Compiling (this may take a while)...
set "CL=/Zm200 %CL%"
python -m nuitka --standalone --output-dir=dist\backend --include-package=fastapi --include-package=uvicorn --include-package=pydantic --include-package=pydantic_settings --include-package=faiss --include-package=numpy --include-module=main --include-module=app --include-data-dir=backend\app=.\app --include-data-dir=backend\data=.\data --output-filename=DiamondMemoryBackend.exe --assume-yes-for-downloads --remove-output backend\main.py

echo.
echo Backend build finished.
echo Output: dist\backend\
dir dist\backend
