@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0)" >nul 2>nul
  if errorlevel 1 goto broken_venv
  exit /b 0
)

rem Execute Python to reject broken PATH entries and Microsoft Store aliases.
python -c "import sys, struct; sys.exit(not (sys.version_info >= (3, 11) and struct.calcsize('P') == 8))" >nul 2>nul
if not errorlevel 1 (
  python -m venv .venv
  if errorlevel 1 exit /b 1
  exit /b 0
)
py -3 -c "import sys, struct; sys.exit(not (sys.version_info >= (3, 11) and struct.calcsize('P') == 8))" >nul 2>nul
if not errorlevel 1 (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
  exit /b 0
)

echo Khong tim thay Python 3.11 tro len, 64-bit chay duoc.
echo Cai Python 64-bit va chon "Add python.exe to PATH" khi cai dat.
echo Sau do dong cua so nay va chay lai run_windows.bat.
echo Neu da cai Python, kiem tra lenh: python --version
exit /b 1

:broken_venv
echo Moi truong .venv hien tai khong chay duoc Python.
echo Doi ten thu muc .venv thanh .venv_old, roi chay lai de tao moi.
exit /b 1
