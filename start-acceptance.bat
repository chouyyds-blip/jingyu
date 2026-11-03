@echo off
cd /d "%~dp0"
if not exist "data\acceptance.db" (
  python tools\prepare_demo.py
  if errorlevel 1 goto end
)
python server.py --db "data\acceptance.db" --port 8000
:end
pause
