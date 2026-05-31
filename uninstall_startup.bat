@echo off
setlocal
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PollenScribe.lnk"

if exist "%SHORTCUT%" (
  del "%SHORTCUT%"
  echo Removed PollenScribe startup shortcut.
) else (
  echo PollenScribe startup shortcut was not found.
)

pause
