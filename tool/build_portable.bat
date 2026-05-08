@echo off
setlocal enabledelayedexpansion

set "PROJECT_NAME=DirCache"

:: ===============================
:: PATHS
:: ===============================
set "TOOL_DIR=%~dp0"
for %%I in ("%TOOL_DIR%..") do set "ROOT=%%~fI\"

set "PYTHON_DIR=%ROOT%build\python"
set "PORTABLE_DIR=%ROOT%dist\%PROJECT_NAME%_Portable"

echo ROOT: %ROOT%
echo PYTHON: %PYTHON_DIR%

:: ===============================
:: CHECK PYTHON
:: ===============================
if not exist "%PYTHON_DIR%\python.exe" (
    echo [ERROR] Python not found: %PYTHON_DIR%
    pause
    exit /b
)

:: ===============================
:: DETECT SITE-PACKAGES
:: ===============================
set "SRC_SITE="

if exist "%ROOT%.venv\Lib\site-packages" set "SRC_SITE=%ROOT%.venv\Lib\site-packages"
if not defined SRC_SITE if exist "%ROOT%venv\Lib\site-packages" set "SRC_SITE=%ROOT%venv\Lib\site-packages"

if not defined SRC_SITE (
    for /f "delims=" %%i in ('python -c "import site; print(site.getsitepackages()[0])"') do set "SRC_SITE=%%i"
)

if not defined SRC_SITE (
    echo [ERROR] site-packages not found
    pause
    exit /b
)

echo Using site-packages: %SRC_SITE%

:: ===============================
:: CLEAN
:: ===============================
if exist "%PORTABLE_DIR%" rd /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%\app"
mkdir "%PORTABLE_DIR%\python\Lib\site-packages"

:: ===============================
:: BUILD RUST (if needed)
:: ===============================
echo Ensuring Rust build...

set "RUST_PROJECT=%ROOT%scanner_core"
set "RUST_DLL=%RUST_PROJECT%\target\release\scanner_core.dll"

if exist "%RUST_DLL%" (
    echo [OK] Rust release exists
) else (
    echo [INFO] Building Rust...
    pushd "%RUST_PROJECT%"
    cargo build --release
    popd

    if not exist "%RUST_DLL%" (
        echo [ERROR] Rust build failed!
        pause
        exit /b
    )
)

:: ===============================
:: COPY APP (ONLY REQUIRED FILES)
:: ===============================
echo Copying app...

copy "%ROOT%*.py" "%PORTABLE_DIR%\app\" >nul

robocopy "%ROOT%ui" "%PORTABLE_DIR%\app\ui" /E >nul
robocopy "%ROOT%assets" "%PORTABLE_DIR%\app\assets" /E >nul

:: ===============================
:: COPY RUST DLL ONLY
:: ===============================
echo Copying Rust DLL...

copy "%RUST_DLL%" "%PORTABLE_DIR%\app\" >nul

:: ===============================
:: COPY PYTHON RUNTIME
:: ===============================
echo Copying Python...
robocopy "%PYTHON_DIR%" "%PORTABLE_DIR%\python" /E >nul

:: ===============================
:: COPY DEPENDENCIES
:: ===============================
echo Copying dependencies...
robocopy "%SRC_SITE%" "%PORTABLE_DIR%\python\Lib\site-packages" /E >nul

:: ===============================
:: CLEAN JUNK
:: ===============================
echo Cleaning unnecessary files...

del /q "%PORTABLE_DIR%\app\*.md" >nul 2>&1
del /q "%PORTABLE_DIR%\app\*.txt" >nul 2>&1

rd /s /q "%PORTABLE_DIR%\app\__pycache__" >nul 2>&1

:: ===============================
:: CREATE LAUNCHER
:: ===============================
echo Creating launcher...

(
echo @echo off
echo cd /d %%~dp0
echo set PATH=%%CD%%\python;%%PATH%%
echo start "" python\pythonw.exe -c "import sys, os, runpy; sys.path.insert(0, os.path.join(os.getcwd(), 'app')); runpy.run_path('app/main.py', run_name='__main__')"
) > "%PORTABLE_DIR%\Launch_DirCache.bat"

:: ===============================
:: CREATE ZIP (TEMP OUTSIDE)
:: ===============================
echo Creating ZIP...

set "TEMP_ZIP=%ROOT%dist\_temp.zip"

if exist "%TEMP_ZIP%" del "%TEMP_ZIP%"

powershell -NoProfile -Command ^
"Compress-Archive -Path '%PORTABLE_DIR%\*' -DestinationPath '%TEMP_ZIP%'"

:: ===============================
:: CREATE INNER PACKAGE
:: ===============================
set "INNER_PACKAGE=%PORTABLE_DIR%\DirCache"
mkdir "%INNER_PACKAGE%" >nul 2>&1

:: ===============================
:: ZIP -> BIN (WITH HEADER)
:: ===============================
echo Creating BIN (simple)...

set "TEMP_ZIP=%ROOT%dist\_temp.zip"

if exist "%TEMP_ZIP%" del "%TEMP_ZIP%"

powershell -NoProfile -Command ^
"Compress-Archive -Path '%PORTABLE_DIR%\*' -DestinationPath '%TEMP_ZIP%'"

set "INNER_PACKAGE=%PORTABLE_DIR%\DirCache"
mkdir "%INNER_PACKAGE%" >nul 2>&1

move "%TEMP_ZIP%" "%INNER_PACKAGE%\DirCache.bin" >nul

:: ===============================
:: COPY INSTALLERS
:: ===============================
copy "%TOOL_DIR%install.ps1" "%INNER_PACKAGE%\" >nul
copy "%TOOL_DIR%install.bat" "%PORTABLE_DIR%\" >nul

echo Cleaning portable folder (final)...

:: Remove app + python folders (they are inside .bin already)
if exist "%PORTABLE_DIR%\app" rd /s /q "%PORTABLE_DIR%\app"
if exist "%PORTABLE_DIR%\python" rd /s /q "%PORTABLE_DIR%\python"

:: Remove launcher
if exist "%PORTABLE_DIR%\Launch_DirCache.bat" del "%PORTABLE_DIR%\Launch_DirCache.bat"


:: ===============================
:: DONE
:: ===============================
echo.
echo =================================
echo ✅ BUILD COMPLETE
echo =================================
echo Output: %PORTABLE_DIR%
echo =================================

pause