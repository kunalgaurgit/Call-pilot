@echo off
setlocal
cd /d "%~dp0"
title Call Pilot update
echo Updating Call Pilot from GitHub. Your .env, bookings and logs are kept.
echo.

rem Git clone: just pull. Whole block is parsed before it runs, so pulling a new update.bat is safe.
if exist .git (
    where git >nul 2>&1 && (
        git pull --ff-only || echo Update failed - see the message above.
        echo.
        echo If run.bat is open, close it and start it again.
        pause
        exit /b
    )
)

rem Zip copy: download the latest main branch and copy it over this folder.
set "TMPD=%TEMP%\callpilot-update-%RANDOM%%RANDOM%"
mkdir "%TMPD%"
echo Downloading...
curl.exe -fsSL -o "%TMPD%\main.zip" https://github.com/kunalgaurgit/Call-pilot/archive/refs/heads/main.zip || goto failed
tar -xf "%TMPD%\main.zip" -C "%TMPD%" || goto failed
set "SRC=%TMPD%\Call-pilot-main"
if not exist "%SRC%\app.py" goto failed
rem ponytail: files deleted upstream are left in place; harmless for this app
robocopy "%SRC%" . /E /XD android tools tests .githooks /XF update.bat .gitignore .gitattributes /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto failed

echo.
echo Updated. If run.bat is open, close it and start it again.
echo Phone app: update it from the app - Settings, Check for updates.
pause
rem Replace this script last, on one line, so cmd never reads the changed file mid-run.
copy /y "%SRC%\update.bat" "%~f0" >nul & rd /s /q "%TMPD%" & exit /b

:failed
echo.
echo Update failed. Check the internet connection and try again.
rd /s /q "%TMPD%" 2>nul
pause
exit /b 1
