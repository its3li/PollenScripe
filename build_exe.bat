@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Running setup first...
  call setup.bat
  if errorlevel 1 exit /b 1
)

echo Building Pith.exe...
REM --add-data bundles the tray icon, which the app loads at runtime rather than
REM drawing; without it the packaged build falls back to a plain drawn icon.
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name Pith --icon pith.ico --add-data "pith.ico;." pith.py
if errorlevel 1 goto fail

if exist .env (
  echo Reminder: copy your .env next to dist\Pith.exe before running it.
  echo This script no longer copies it for you, so a real key never lands in dist\.
) else (
  echo No .env found. Create one next to dist\Pith.exe before running the exe.
)

echo.
echo Build complete: dist\Pith.exe
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
