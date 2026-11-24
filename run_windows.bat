@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ensure_python.bat"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -c "import PySide6, PIL, yaml" >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe main.py
if errorlevel 1 goto fail
exit /b 0
:fail
 echo Khong khoi dong duoc. Doc loi phia tren va README.md.
pause
exit /b 1
