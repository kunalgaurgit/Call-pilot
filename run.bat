@echo off
cd /d "%~dp0"
set CALLPILOT_PORT=8001
python -m pip install -q -r requirements.txt

netsh advfirewall firewall show rule name="CallPilot" >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -Command netsh advfirewall firewall add rule name=CallPilot dir=in action=allow protocol=TCP localport=8001 profile=any; netsh advfirewall firewall add rule name=CallPilot dir=in action=allow protocol=UDP localport=8002 profile=any'"
)

echo Phone app: connect to the laptop hotspot (server 192.168.137.1:8001) or the same Wi-Fi
ipconfig | findstr IPv4

start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:8001"
python -m uvicorn app:app --host 0.0.0.0 --port 8001
pause
