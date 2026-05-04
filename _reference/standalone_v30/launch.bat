@echo off
set PORT=8000
pip install fastapi uvicorn pydantic bcrypt Pillow httpx >nul 2>&1
cd backend
start /B python main.py
:loop
curl -s http://localhost:%PORT% >nul
if %errorlevel% neq 0 (
    timeout /t 1 /nobreak >nul
    goto loop
)
start msedge --app=http://localhost:%PORT% --window-size=1200,900
exit
