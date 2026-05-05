@echo off
REM 下载 Ollama 二进制到 build 目录 - Windows 版
REM 在打包前运行，确保 Ollama 二进制文件存在

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set BUILD_DIR=%PROJECT_DIR%\build\ollama\win

echo 准备 Ollama 二进制文件 (Windows)...

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

if exist "%BUILD_DIR%\ollama.exe" (
    echo Ollama 二进制已存在: %BUILD_DIR%\ollama.exe
    exit /b 0
)

echo 正在下载 Ollama for Windows...

set OLLAMA_URL=https://ollama.com/download/ollama-windows-amd64.zip
set TEMP_FILE=%BUILD_DIR%\ollama.zip

curl -L -o "%TEMP_FILE%" "%OLLAMA_URL%" || (
    echo 下载 Ollama 失败！
    echo 请手动下载 Ollama 并放置到: %BUILD_DIR%\ollama.exe
    echo 下载地址: https://ollama.com/download/windows
    del /f "%TEMP_FILE%" 2>nul
    exit /b 1
)

echo 正在解压...
powershell -Command "Expand-Archive -Path '%TEMP_FILE%' -DestinationPath '%BUILD_DIR%' -Force" || (
    echo 解压失败，请手动解压 ollama.zip
    exit /b 1
)

del /f "%TEMP_FILE%" 2>nul

if exist "%BUILD_DIR%\ollama.exe" (
    echo Ollama 下载完成: %BUILD_DIR%\ollama.exe
) else if exist "%BUILD_DIR%\ollama\ollama.exe" (
    move "%BUILD_DIR%\ollama\ollama.exe" "%BUILD_DIR%\ollama.exe"
    echo Ollama 下载完成: %BUILD_DIR%\ollama.exe
) else (
    echo 警告: 未找到 ollama.exe，请手动放置到 %BUILD_DIR%\ollama.exe
)

exit /b 0
