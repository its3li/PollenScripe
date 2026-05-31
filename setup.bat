@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail

echo Installing dependencies...
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 goto fail

if not exist .env (
  if exist .env.example (
    copy .env.example .env >nul
    echo Created .env from .env.example. Edit .env and add your API key before running.
  )
)

echo.
echo Setup complete.
echo Run start.bat to launch PollenScribe.
pause
exit /b 0

:fail
echo.
echo Setup failed.
pause
exit /b 1
