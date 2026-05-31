@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Running setup first...
  call setup.bat
  if errorlevel 1 exit /b 1
)

echo Building PollenScribe.exe...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name PollenScribe --icon PollenScripe.ico pollenscribe.py
if errorlevel 1 goto fail

if exist .env (
  copy .env dist\.env >nul
  echo Copied .env to dist\.env for local testing. Do not publish dist\.env.
) else (
  echo No .env found. Create one next to dist\PollenScribe.exe before running the exe.
)

echo.
echo Build complete: dist\PollenScribe.exe
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
