@echo off
setlocal enabledelayedexpansion

:: --- Configuration ---
set "PROJECT_NAME=DirCache"
set "PYTHON_VENV_EXE=.venv\Scripts\python.exe"
:: ---------------------

echo ===================================================
echo   DirCache Automated Builder
echo ===================================================

echo [1/5] Cleaning previous builds...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo [2/5] Building Standalone Bundle (PyInstaller)...
"%PYTHON_VENV_EXE%" -m PyInstaller --noconfirm --onedir --windowed --onefile^
    --add-data "ui;ui" ^
    --add-data "assets;assets" ^
    --icon "assets/logo.png" ^
    --name "%PROJECT_NAME%" ^
    main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)