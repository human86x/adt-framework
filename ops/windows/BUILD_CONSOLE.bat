@echo off
echo ========================================
echo    ADT FRAMEWORK - CONSOLE BUILDER
echo ========================================
echo.

:: 1. Fix Rust Toolchain
echo [+] Ensuring Rust toolchain is configured...
"%USERPROFILE%\.cargo\bin\rustup" default stable
if %errorlevel% neq 0 (
    echo [+] Installing stable toolchain...
    "%USERPROFILE%\.cargo\bin\rustup" toolchain install stable
    "%USERPROFILE%\.cargo\bin\rustup" default stable
)

:: 2. Navigate to adt-console
cd /d "%~dp0..\..\adt-console"
echo [DEBUG] Current Dir: %cd%

:: 3. Ensure Tauri CLI is installed
echo [+] Checking for Tauri CLI...
:: Using full path to cargo to avoid shim errors
"%USERPROFILE%\.cargo\bin\cargo" install tauri-cli --version 2.1.0

:: 4. Run Build
echo.
echo [+] Starting Tauri Production Build...
echo     (This may take several minutes)
"%USERPROFILE%\.cargo\bin\cargo" tauri build

if %errorlevel% neq 0 (
    echo [!] Build failed with error code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] Console built successfully.
echo Binary location: src-tauri\target\release\adt-console.exe
pause
