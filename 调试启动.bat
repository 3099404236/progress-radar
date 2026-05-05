@echo off
chcp 65001 >nul
cd /d "C:\Users\z3099\Desktop\大三下学期\进度条"
echo === ProgressRadar 调试模式（保留控制台） ===
echo 日志同时写到 data\app.log
echo.
"D:\anaconda\python.exe" main.py --debug
echo.
echo === 进程已退出，按任意键关闭 ===
pause >nul
