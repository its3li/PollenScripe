@echo off
setlocal
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\Pith.lnk"
set "LEGACY=%STARTUP%\PollenScribe.lnk"

if exist "%SHORTCUT%" (
  del "%SHORTCUT%"
  echo Removed Pith startup shortcut.
) else (
  echo Pith startup shortcut was not found.
)

REM Left behind by the pre-rename builds, and it points at an exe that no longer
REM gets rebuilt, so a stale copy would start the old app every sign-in.
if exist "%LEGACY%" (
  del "%LEGACY%"
  echo Removed the old PollenScribe startup shortcut too.
)

pause
