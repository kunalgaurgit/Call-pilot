@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:8001"
python -m uvicorn app:app --host 127.0.0.1 --port 8001
pause
