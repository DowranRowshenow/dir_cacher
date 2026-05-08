@echo off
setlocal

echo Installing DirCache...
echo.

REM Get script directory
set "HERE=%~dp0"

REM Run PowerShell installer with bypass
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%/DirCache/install.ps1"

echo.
echo Installation finished.
pause