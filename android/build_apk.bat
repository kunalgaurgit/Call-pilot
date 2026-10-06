@echo off
rem Builds the signed release APK. Uses the portable JDK/SDK from D:\Victoris\.tools if present;
rem teammates can instead open this folder in Android Studio (it supplies its own JDK and SDK).
cd /d "%~dp0"
if exist D:\Victoris\.tools\jdk21 set JAVA_HOME=D:\Victoris\.tools\jdk21
if not exist local.properties if exist D:\Victoris\.tools\sdk echo sdk.dir=D\:/Victoris/.tools/sdk> local.properties
call gradlew.bat assembleRelease --console=plain || exit /b 1
echo APK: %~dp0app\build\outputs\apk\release\app-release.apk
