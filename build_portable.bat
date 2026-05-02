@echo off
setlocal

set "PROJECT_NAME=DirCache"
set "PORTABLE_DIR=dist\%PROJECT_NAME%_Portable"

echo ===================================================
echo   DirCache Portable Builder (Source + Python)
echo ===================================================

echo [1/3] Cleaning portable folder...
if exist "%PORTABLE_DIR%" rd /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%\app"
mkdir "%PORTABLE_DIR%\python"

echo [2/3] Syncing application files...
robocopy . "%PORTABLE_DIR%\app" /E /XF *.db *.log *.spec *.exe *.bat /XD .git build dist __pycache__ .venv >nul
echo [SUCCESS] App source synced.

echo [3/3] Syncing Python environment (this may take a minute)...
robocopy "..\.venv" "%PORTABLE_DIR%\python" /E /MT:16 /NFL /NDL >nul
copy "logo.ico" "%PORTABLE_DIR%\app\logo.ico" >nul
:: Use a renamed interpreter to force a unique taskbar identity
copy "%PORTABLE_DIR%\python\Scripts\pythonw.exe" "%PORTABLE_DIR%\python\Scripts\DirCache.exe" >nul

echo Creating launcher...
(
echo @echo off
echo cd /d %%~dp0
echo start "" "python\Scripts\DirCache.exe" "app\main.py"
echo exit
) > "%PORTABLE_DIR%\Launch_DirCache.bat"

echo Creating Windows Shortcut...
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%PORTABLE_DIR%\DirCache.lnk');$s.TargetPath='cmd.exe';$s.Arguments='/c Launch_DirCache.bat';$s.WorkingDirectory='%~dp0%PORTABLE_DIR%';$s.IconLocation='%~dp0%PORTABLE_DIR%\app\logo.ico';$s.WindowStyle=7;$s.Save()"

echo.
echo ===================================================
echo   PORTABLE BUILD COMPLETE!
echo   Location: %PORTABLE_DIR%\
echo ===================================================
pause
