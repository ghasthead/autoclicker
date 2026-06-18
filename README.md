Go to the Releases page and download AutoClicker.exe.

Windows Defender warning: Because this app is not commercially signed, Windows may show a blue "Windows protected your PC" screen. Click More info → Run anyway. This is normal for self-built tools.

Building from source

Requirements: Python 3.8+ and pip
-----------------------------------------------
YOU MUST HAVE PYTHON INSTALLED FOR THIS TO WORK
-----------------------------------------------
Install dependencies:

pip install keyboard mouse pyinstaller
Build the .exe:

python -m PyInstaller --onefile --windowed --noconsole --name "AutoClicker" --hidden-import=keyboard --hidden-import=mouse autoclicker.py
Your app will be at dist\AutoClicker.exe (dist folder)

Or just double-click BUILD_ME.bat and it handles everything automatically.

Default Hotkeys

Action	Default Key
Toggle autoclicker	F6
Force quit app	F12
Toggle macro recording	F8
Toggle macro playback	F9
All hotkeys are rebindable from inside the app.

Notes

Run as Administrator if hotkeys don't work in certain games or elevated windows
Macro files (macros.json) are saved in the same folder as the .exe
Closing the window exits the app; the hotkey still works while the window is minimised

this application is a 3 in 1: autoclicker, cps (clicks per second) tester, and macro


update, 6/18, added more features

youtube installation guide:
https://youtu.be/NI4QSImrDrg
