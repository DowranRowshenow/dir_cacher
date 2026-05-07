@echo off
setlocal enabledelayedexpansion

set "PROJECT_NAME=DirCache"
set "PORTABLE_DIR=dist\%PROJECT_NAME%_Portable"
set "PYTHON_DIR=python"

echo ===================================================
echo   DirCache Portable Builder (FINAL FAST)
echo ===================================================

:: -------------------------------
:: 1. Ensure Python runtime exists
:: -------------------------------
if not exist "%PYTHON_DIR%\python.exe" (
    echo [INFO] Python not found. Downloading embeddable runtime...

    mkdir "%PYTHON_DIR%"

    powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.13.3/python-3.13.3-embed-amd64.zip -OutFile python_embed.zip"

    powershell -NoProfile -Command ^
    "Expand-Archive python_embed.zip -DestinationPath python"

    del python_embed.zip

    echo [INFO] Configuring python313._pth...
    (
        echo python313.zip
        echo .
        echo Lib
        echo Lib\site-packages
        echo.
        echo import site
    ) > "%PYTHON_DIR%\python313._pth"
)

:: -------------------------------
:: 2. Detect existing environment
:: -------------------------------
echo [INFO] Detecting local environment...

set "SRC_SITE="

if exist ".venv\Lib\site-packages" (
    set "SRC_SITE=.venv\Lib\site-packages"
)

if not defined SRC_SITE if exist "venv\Lib\site-packages" (
    set "SRC_SITE=venv\Lib\site-packages"
)

if not defined SRC_SITE if exist "env\Lib\site-packages" (
    set "SRC_SITE=env\Lib\site-packages"
)

:: fallback: detect from active python
if not defined SRC_SITE (
    echo [INFO] Trying to detect from active Python interpreter...

    for /f "delims=" %%i in ('python -c "import site; print(site.getsitepackages()[0])"') do (
        set "SRC_SITE=%%i"
    )
)

if not defined SRC_SITE (
    echo [ERROR] Could not find any site-packages location!
    pause
    exit /b
)

echo [INFO] Using site-packages: %SRC_SITE%

:: -------------------------------
:: 3. Clean output
:: -------------------------------
echo [1/3] Cleaning output...
if exist "%PORTABLE_DIR%" rd /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%\app"
mkdir "%PORTABLE_DIR%\python\Lib\site-packages"

:: -------------------------------
:: 4. Copy application
:: -------------------------------
echo [2/3] Copying app...
robocopy . "%PORTABLE_DIR%\app" /E ^
 /XF *.db *.log *.spec *.exe *.bat *.md *.json ^
 /XD .git build dist __pycache__ .venv python >nul

:: -------------------------------
:: 5. Copy Python runtime
:: -------------------------------
echo [3/3] Copying Python runtime...
robocopy "%PYTHON_DIR%" "%PORTABLE_DIR%\python" /E /MT:16 /NFL /NDL >nul

:: -------------------------------
:: 6. Copy dependencies (FAST ✅)
:: -------------------------------
echo [INFO] Copying dependencies...
robocopy "%SRC_SITE%" "%PORTABLE_DIR%\python\Lib\site-packages" /E /MT:16 /NFL /NDL >nul

:: -------------------------------
:: 7. Copy icon
:: -------------------------------
if not exist "%PORTABLE_DIR%\app\assets" mkdir "%PORTABLE_DIR%\app\assets"
copy "assets\logo.ico" "%PORTABLE_DIR%\app\assets\" >nul

:: -------------------------------
:: 8. Create launcher (FINAL)
:: -------------------------------
echo Creating launcher...

(
echo @echo off
echo cd /d %%~dp0
echo.
echo set PATH=%%CD%%\python;%%CD%%\python\Lib\site-packages\PySide6;%%PATH%%
echo.
echo start "" python\pythonw.exe -c "import sys, os, runpy; sys.path.insert(0, os.path.join(os.getcwd(), 'app')); runpy.run_path('app/main.py', run_name='__main__')"
echo exit
) > "%PORTABLE_DIR%\Launch_DirCache.bat"

:: -------------------------------
:: 9. Create shortcut
:: -------------------------------
echo Creating shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$p='%CD%\%PORTABLE_DIR%';$s=(New-Object -COM WScript.Shell).CreateShortcut($p+'\DirCache.lnk');$s.TargetPath='cmd.exe';$s.Arguments='/c Launch_DirCache.bat';$s.WorkingDirectory=$p;$s.IconLocation=$p+'\app\assets\logo.ico';$s.WindowStyle=7;$s.Save()"

echo.
echo ===================================================
echo   BUILD COMPLETE ✅
echo   Location: %PORTABLE_DIR%
echo ===================================================
pause