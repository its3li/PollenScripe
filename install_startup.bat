@echo off
setlocal
cd /d "%~dp0"

set "EXE=%~dp0dist\Pith.exe"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\Pith.lnk"

if not exist "%EXE%" (
  echo dist\Pith.exe was not found.
  echo Run build_exe.bat first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut('%SHORTCUT%'); $shortcut.TargetPath = '%EXE%'; $shortcut.WorkingDirectory = '%~dp0dist'; $shortcut.WindowStyle = 7; $shortcut.Description = 'Start Pith when Windows starts'; $shortcut.Save()"
if errorlevel 1 goto fail

REM Drop the pre-rename shortcut, so upgrading does not leave two copies starting
REM at sign-in.
if exist "%STARTUP%\PollenScribe.lnk" del "%STARTUP%\PollenScribe.lnk"

echo Pith will now start when you sign in to Windows.
echo Shortcut: %SHORTCUT%
pause
exit /b 0

:fail
echo Failed to create startup shortcut.
pause
exit /b 1
