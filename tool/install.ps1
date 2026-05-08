# ================================
# DirCache Installer (PowerShell)
# ================================

$ErrorActionPreference = "Stop"

# --- Config ---
$APP_NAME    = "DirCache"
$ARCHIVE     = "DirCache_Portable"
$HERE        = Split-Path -Parent $MyInvocation.MyCommand.Path
$INSTALL_DIR = Join-Path $env:LOCALAPPDATA "Programs\$APP_NAME"

# Reliable Desktop path (handles OneDrive)
$DESKTOP = [Environment]::GetFolderPath("Desktop")

Write-Host "Installing $APP_NAME..." -ForegroundColor Cyan
Write-Host ""

# --- Progress helper ---
function Show-Progress($percent, $text) {
    Write-Progress -Activity "$APP_NAME Installer" -Status $text -PercentComplete $percent
}

# --- Step 1 ---
Show-Progress 10 "Starting..."
Start-Sleep 1

# --- Step 2: Extract ---
Write-Host "Extracting..."

$archive = Join-Path $PSScriptRoot "DirCache.bin"

if (!(Test-Path $archive)) {
    Write-Host "❌ ZIP not found: $archive" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null

# Unblock file (important in corporate environment)
Unblock-File $archive -ErrorAction SilentlyContinue

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($archive, $INSTALL_DIR)
    Write-Host "✅ Extracted successfully"
}
catch {
    Write-Host "❌ Extraction failed (REAL ERROR BELOW):" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    exit 1
}

# --- Step 3 ---
Show-Progress 60 "Setting up..."
Start-Sleep 1

# --- Paths ---
$target = Join-Path $INSTALL_DIR "Launch_DirCache.bat"
$icon   = Join-Path $INSTALL_DIR "app\assets\logo.ico"

if (!(Test-Path $icon)) {
    $icon = Join-Path $env:SystemRoot "System32\shell32.dll"
}

# --- Shortcut function (robust) ---
function Create-Shortcut($path) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($path)
    $sc.TargetPath       = $target
    $sc.WorkingDirectory = $INSTALL_DIR
    $sc.IconLocation     = $icon
    $sc.Save()
}

# --- Step 4: Desktop shortcut ---
Show-Progress 75 "Creating Desktop shortcut..."

$desktopCandidates = @(
    $DESKTOP,
    "$env:USERPROFILE\Desktop",
    "$env:PUBLIC\Desktop"
)

$desktopCreated = $false

foreach ($path in $desktopCandidates) {
    try {
        if (!(Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }

        $shortcutPath = Join-Path $path "$APP_NAME.lnk"
        Create-Shortcut $shortcutPath

        Write-Host "Desktop shortcut: $shortcutPath"
        $desktopCreated = $true
        break
    }
    catch {}
}

if (-not $desktopCreated) {
    Write-Host "⚠ Desktop shortcut failed" -ForegroundColor Yellow
}

# --- Step 5: Start Menu shortcut ---
Show-Progress 90 "Adding to Start Menu..."

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$appFolder = Join-Path $startMenu $APP_NAME

try {
    if (!(Test-Path $appFolder)) {
        New-Item -ItemType Directory -Path $appFolder -Force | Out-Null
    }

    $startShortcut = Join-Path $appFolder "$APP_NAME.lnk"
    Create-Shortcut $startShortcut

    Write-Host "Start Menu shortcut: $startShortcut"
}
catch {
    Write-Host "⚠ Start Menu shortcut failed" -ForegroundColor Yellow
}

# --- Done ---
Show-Progress 100 "Complete"
Start-Sleep 1

Write-Host ""
Write-Host "✅ Installation complete!" -ForegroundColor Green
