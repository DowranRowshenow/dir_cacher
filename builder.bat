@echo off
setlocal enabledelayedexpansion

:: --- Configuration ---
set "PROJECT_NAME=DirCache"
set "PYTHON_VENV_EXE=..\.venv\Scripts\python.exe"
set "SIGNTOOL=C:\Users\u49587\AppData\Local\Programs\signtool\signtool.exe"
set "CERT_NAME=zeroteams"
:: ---------------------

echo ===================================================
echo   DirCache Automated Builder
echo ===================================================

echo [1/5] Cleaning previous builds...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo [2/5] Building Standalone Bundle (PyInstaller)...
"%PYTHON_VENV_EXE%" -m PyInstaller --noconfirm --onedir --windowed ^
    --add-data "ui;ui" ^
    --add-data "logo.png;." ^
    --icon "logo.png" ^
    --name "%PROJECT_NAME%" ^
    main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo [3/5] Signing the Executable...
if exist "%SIGNTOOL%" (
    "%SIGNTOOL%" sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /n "%CERT_NAME%" "dist\%PROJECT_NAME%\%PROJECT_NAME%.exe"
    if %ERRORLEVEL% EQU 0 (
        echo [SUCCESS] Executable signed with %CERT_NAME%
    ) else (
        echo [WARNING] Signing failed. Check if certificate is installed.
    )
) else (
    echo [SKIP] Signtool not found at specified path.
)

echo [4/5] Preparing Portable Source Distribution...
echo Creating structure...
mkdir "dist\%PROJECT_NAME%_Portable\app" >nul 2>&1
mkdir "dist\%PROJECT_NAME%_Portable\python" >nul 2>&1

echo Copying app source...
robocopy . "dist\%PROJECT_NAME%_Portable\app" /E /XF *.db *.log *.spec *.exe *.bat /XD .git build dist __pycache__ .venv >nul

echo Copying bundled python (this will take a moment)...
robocopy "..\.venv" "dist\%PROJECT_NAME%_Portable\python" /E /MT:16 /NFL /NDL >nul
copy "logo.ico" "dist\%PROJECT_NAME%_Portable\app\logo.ico" >nul

echo [5/5] Adding Portable Launcher...
(
echo @echo off
echo cd /d %%~dp0
echo start "" "python\Scripts\pythonw.exe" "app\main.py"
echo exit
) > "dist\%PROJECT_NAME%_Portable\Launch_DirCache.bat"

echo Creating Windows Shortcut...
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('dist\%PROJECT_NAME%_Portable\DirCache.lnk');$s.TargetPath='cmd.exe';$s.Arguments='/c Launch_DirCache.bat';$s.WorkingDirectory='%~dp0dist\%PROJECT_NAME%_Portable';$s.IconLocation='%~dp0dist\%PROJECT_NAME%_Portable\app\logo.ico';$s.WindowStyle=7;$s.Save()"

echo.
echo ===================================================
echo   BUILD COMPLETE!
echo.
echo   1. Signed Bundle: dist\%PROJECT_NAME%\
echo   2. Portable Source: dist\%PROJECT_NAME%_Portable\
echo ===================================================
pause
