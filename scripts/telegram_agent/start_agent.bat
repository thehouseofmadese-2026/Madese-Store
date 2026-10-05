@echo off
cd /d "%~dp0"
:loop
python bot.py
echo Bot stopped. Restarting in 10s... (close this window to quit)
timeout /t 10 >nul
goto loop
