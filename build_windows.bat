@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ensure_python.bat"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m compileall -q app main.py
if errorlevel 1 goto fail
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe -m pytest -q
if errorlevel 1 goto fail
set QT_QPA_PLATFORM=
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name "Tools by hkhang17pls" main.py
if errorlevel 1 goto fail
 echo Build complete. See dist folder.
pause
exit /b 0
:fail
 echo Build failed. See errors above.
pause
exit /b 1
