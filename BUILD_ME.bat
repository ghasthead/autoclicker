@echo off
title Echo AutoClicker — Builder
color 0B

echo.
echo  ============================================
echo   Echo AutoClicker .EXE Builder
echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Download from https://python.org
    echo  During install check "Add Python to PATH"
    pause & exit /b 1
)

echo  [1/4] Installing packages...
python -m pip install --upgrade pip --quiet
python -m pip install keyboard mouse pyautogui pyinstaller pillow --quiet

echo  [2/4] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist Echo.spec del Echo.spec

echo  [3/4] Building Echo.exe...
echo.

python -m PyInstaller --onefile --windowed --noconsole --name "Echo" ^
  --icon=echo_icon.ico ^
  --hidden-import=keyboard ^
  --hidden-import=mouse ^
  --hidden-import=pyautogui ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  --hidden-import=PIL.ImageDraw ^
  --hidden-import=PIL.ImageTk ^
  --hidden-import=PIL._tkinter_finder ^
  --collect-all PIL ^
  autoclicker.py

if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed. Read above for details.
    pause & exit /b 1
)

echo.
echo  [4/4] Done! Your app: dist\Echo.exe
echo.
echo  ============================================
echo   IMPORTANT - if the taskbar icon looks wrong
echo  ============================================
echo  Windows caches exe icons by file path. If you
echo  unpin/re-pin or rebuild and the OLD icon still
echo  shows up, do this:
echo    1. Unpin Echo from the taskbar
echo    2. Delete  dist\Echo.exe
echo    3. Run this builder again
echo    4. Open the NEW dist\Echo.exe once, THEN pin it
echo  If it still shows the wrong icon, clear the
echo  Windows icon cache: open Run (Win+R), type
echo    ie4uinit.exe -ClearIconCache
echo  then restart Explorer (or just reboot).
echo.
pause