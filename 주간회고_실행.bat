@echo off
cd /d "%~dp0"
"C:\Users\playdata2\miniconda3\python.exe" main.py
if errorlevel 1 (
    echo.
    echo Error occurred. See message above.
    pause
)
