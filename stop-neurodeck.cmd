@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-neurodeck.ps1"
set "NEURODECK_EXIT=%ERRORLEVEL%"
if not "%NEURODECK_EXIT%"=="0" pause
exit /b %NEURODECK_EXIT%
