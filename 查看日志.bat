@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "data\app.log" (
    notepad "data\app.log"
) else (
    echo 还没有日志（程序尚未启动过）
    pause
)
