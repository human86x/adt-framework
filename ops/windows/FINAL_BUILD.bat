@echo off
echo --- ADT DEBUG START ---
pause

echo [+] Checking for Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Node.js missing. Attempting install...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 echo [!] Winget install failed. Please install Node.js manually.
)
pause

echo [+] Checking for Rust...
if not exist "%USERPROFILE%\.cargo\bin\rustc.exe" (
    echo [!] Rust missing. Attempting install...
    curl -sLo rustup-init.exe https://win.rustup.rs/x86_64
    .\rustup-init.exe -y --default-toolchain stable
    del rustup-init.exe
)
pause

echo [+] Navigating to Project Root...
cd /d "%~dp0..\.."
echo Current Dir: %cd%
pause

echo [+] Building Python Components...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate
pip install flask requests markdown markupsafe pyinstaller
pyinstaller --clean --noconfirm ops\windows\dttp_service.spec
pyinstaller --clean --noconfirm ops\windows\adt_center.spec
pause

echo [+] Building Console...
cd adt-console
npm install && npm run tauri build
pause

echo [+] Finalizing...
echo Finished.
pause
