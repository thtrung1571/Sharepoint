@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "APP_NAME=AutoMailSender"
set "MAIN=main.py"
set "BROWSERS_DIR=%SCRIPT_DIR%browsers"

echo ============================================
echo   Auto Mail Sender - Build Script (Onedir)
echo ============================================
echo.

echo [1/6] Checking pip packages...
pip show pyinstaller >nul 2>&1 || pip install pyinstaller
pip show pyside6 >nul 2>&1 || pip install pyside6
pip show playwright >nul 2>&1 || pip install playwright
pip show python-dotenv >nul 2>&1 || pip install python-dotenv

echo.
echo [2/6] Installing Playwright browsers...
python -m playwright install chromium --with-deps

echo.
echo [3/6] Cleaning old builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"
if exist "%BROWSERS_DIR%" rmdir /s /q "%BROWSERS_DIR%"

echo.
echo [4/6] Copying browsers to build folder...
mkdir "%BROWSERS_DIR%"
xcopy /e /i /y "%LOCALAPPDATA%\ms-playwright" "%BROWSERS_DIR%\" >nul 2>&1

echo.
echo [5/6] Running PyInstaller (onedir mode)...
if exist "window.png" (
    set "ICON_FLAG=--icon=window.png"
) else (
    set "ICON_FLAG="
)

pyinstaller ^
    --name=%APP_NAME% ^
    --onedir ^
    --windowed ^
    %ICON_FLAG% ^
    --clean ^
    --noconfirm ^
    --add-data ".env;." ^
    --add-data "config.json;." ^
    --add-data "%BROWSERS_DIR%;browsers" ^
    --hidden-import=playwright ^
    --hidden-import=dotenv ^
    --hidden-import=email.header ^
    --hidden-import=email.mime.multipart ^
    --hidden-import=email.mime.base ^
    --hidden-import=email.mime.text ^
    --hidden-import=email ^
    --hidden-import=encoders ^
    --hidden-import=smtplib ^
    --hidden-import=zipfile ^
    --collect-all=playwright ^
    %MAIN%

echo.
echo [6/6] Post-build copy config files...
if not exist "dist\%APP_NAME%" mkdir "dist\%APP_NAME%"
copy ".env" "dist\%APP_NAME%\.env" >nul 2>&1
copy "config.json" "dist\%APP_NAME%\config.json" >nul 2>&1

echo.
if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
    echo ============================================
    echo   SUCCESS
    echo   Output: %SCRIPT_DIR%dist\%APP_NAME%\%APP_NAME%.exe
    echo ============================================
) else (
    echo ============================================
    echo   FAILED - Check errors above
    echo ============================================
)

pause
