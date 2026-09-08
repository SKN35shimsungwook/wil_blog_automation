@echo off
REM Builds dist\WIL_Automation.exe (single file). Run from this folder.
REM Uses an isolated venv so unrelated packages (torch, pandas...) from the
REM global Python env are not bundled into the exe.
cd /d "%~dp0"

if not exist ".build-venv\Scripts\python.exe" (
  python -m venv .build-venv
  if errorlevel 1 goto :fail
)
".build-venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".build-venv\Scripts\python.exe" -m pip install --quiet -r requirements-build.txt
if errorlevel 1 goto :fail

".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WIL_Automation ^
  --collect-submodules markdown.extensions ^
  main.py
if errorlevel 1 goto :fail

echo.
echo Done: dist\WIL_Automation.exe
exit /b 0

:fail
echo BUILD FAILED
exit /b 1
