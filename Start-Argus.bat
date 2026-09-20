@echo off
REM Argus AI - one-click local demo (API + Kit stream + dashboard)
REM Double-click this file, or run: Start-Argus.bat
REM To free ports 8000/3000 first: Start-Argus.bat -Force

setlocal
cd /d "%~dp0"

set "FORCE="
if /I "%~1"=="-Force" set "FORCE=-Force"
if /I "%~1"=="/Force" set "FORCE=-Force"
if /I "%~1"=="force" set "FORCE=-Force"

echo.
echo  Argus AI - starting API, Omniverse Kit stream, and dashboard...
echo  Kit is HEADLESS: no Omniverse editor window will appear.
echo  Look for a console titled "Argus AI Kit Streaming" and Live in the browser.
echo  Close the three service windows to shut everything down.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\demo_launch.ps1" %FORCE%
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo Launch finished with errors. See tools\demo_logs\ and the service windows.
) else (
  echo Launch script finished. Keep the service windows open while you use the app.
)
echo.
pause
endlocal
exit /b %ERR%
