@echo off
echo --- ADT Framework Windows Build ---
echo.

if not exist "venv\Scriptsctivate" (
    echo [!] Python venv not found. Please run this from project root with venv active.
    pause
    exit /b 1
)

echo [+] Installing build dependencies...
pip install pyinstaller

echo.
echo [+] Building DTTP Service...
pyinstaller --clean --noconfirm ops\windows\dttp_service.spec

echo.
echo [+] Building Operational Center...
pyinstaller --clean --noconfirm ops\windowsdt_center.spec

echo.
echo [=] Build complete.
echo     Binaries are in distdt_dttp_service and distdt_operational_center
pause
