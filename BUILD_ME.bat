@echo off
title AutoClicker Pro — Builder
color 0B

echo.
echo  ============================================
echo   AutoClicker Pro .EXE Builder
echo  ============================================
echo.

echo  Checking Python...
python --version
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found!
    echo  Download from: https://www.python.org/downloads/
    echo  During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo.
echo  [1/3] Installing packages...
python -m pip install --upgrade pip
python -m pip install keyboard mouse pyinstaller
echo.

if errorlevel 1 (
    echo  [ERROR] Package install failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo  [2/3] Building AutoClicker.exe...
echo  (this takes 30-90 seconds, please wait)
echo.

python -m PyInstaller --onefile --windowed --noconsole --name "AutoClicker" --hidden-import=keyboard --hidden-import=mouse autoclicker.py

echo.
echo  PyInstaller exit code: %errorlevel%
echo.

if errorlevel 1 (
    echo  [ERROR] Build failed. Read the output above for details.
    echo.
    pause
    exit /b 1
)

echo  [3/3] SUCCESS!
echo.
echo  Your app is here:  dist\AutoClicker.exe
echo.
echo  You can move AutoClicker.exe anywhere you like.
echo.
pause