@echo off
setlocal
cd /d "%~dp0"
title Call Pilot server
if not defined CALLPILOT_PORT set CALLPILOT_PORT=8001

rem ---- 1. Python 3.10+ (first run on a new PC may need to install it) ----
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto python_ok
echo Call Pilot needs Python 3.10 or newer, and it was not found on this PC.
where winget >nul 2>&1
if errorlevel 1 goto python_manual
choice /m "Install Python 3.13 now (free, from Microsoft's winget)"
if errorlevel 2 goto python_manual
winget install -e --id Python.Python.3.13 --scope user
echo.
echo Python is installed. Close this window and double-click run.bat again.
pause
exit /b
:python_manual
echo Install it from https://www.python.org/downloads/
echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then run this file again.
pause
exit /b 1
:python_ok

rem ---- 2. Python packages (quick when already installed) ----
echo Checking Python packages...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Installing packages failed - check the internet connection and run this again.
    pause
    exit /b 1
)

rem ---- 3. First run: create .env with the Gemini key ----
if exist .env goto env_ok
echo.
echo ===== First-time setup =====
echo Call Pilot talks using Google Gemini. Get a free API key at:
echo     https://aistudio.google.com/apikey
echo Without a key it runs in offline demo mode (scripted replies).
echo.
set "GEMINI_KEY="
set /p "GEMINI_KEY=Paste your Gemini API key and press Enter (or just press Enter for demo mode): "
if defined GEMINI_KEY (
    > .env echo GEMINI_API_KEY=%GEMINI_KEY%
    >> .env echo GEMINI_MODEL=gemini-3.5-flash,gemini-3.1-flash-lite
    >> .env echo LLM_MODE=gemini
    echo Saved. To change the key later, edit .env or delete it and run this again.
) else (
    > .env echo LLM_MODE=fake
    echo Demo mode saved. To add a key later, delete .env and run this again.
)
set "GEMINI_KEY="
:env_ok

rem ---- 4. Firewall: let the phone reach this PC (asks for admin once) ----
netsh advfirewall firewall show rule name="CallPilot" >nul 2>&1
if errorlevel 1 (
    echo Allowing the phone app through Windows Firewall - click Yes on the admin prompt.
    powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -Command netsh advfirewall firewall add rule name=CallPilot dir=in action=allow protocol=TCP localport=%CALLPILOT_PORT% profile=any; netsh advfirewall firewall add rule name=CallPilot dir=in action=allow protocol=UDP localport=8002 profile=any'"
)

rem ---- 5. Start ----
echo.
echo ================================================================
echo  Call Pilot is starting on port %CALLPILOT_PORT%
echo  Browser:   http://127.0.0.1:%CALLPILOT_PORT%   (dashboard: /dashboard.html)
echo  Phone app: install the APK from the "release" folder, or from
echo             https://github.com/kunalgaurgit/Call-pilot/releases/latest
echo             then join the same Wi-Fi as this PC (or this PC's hotspot).
echo             It finds the server by itself. This PC's addresses:
ipconfig | findstr IPv4
echo  Keep this window open while using the app. Close it to stop.
echo ================================================================
echo.

start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%CALLPILOT_PORT%"
python -m uvicorn app:app --host 0.0.0.0 --port %CALLPILOT_PORT%
pause
