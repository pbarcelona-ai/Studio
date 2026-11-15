@echo off
rem Start Pistachio's Studio on Windows (double-click this file, or run it in a terminal). It opens the page in your browser.
rem install.bat makes .venv with everything the Studio needs. Close this window, or press Ctrl+C, to stop the Studio.
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo The Studio is not installed yet: double-click install.bat first.
  pause
  exit /b 1
)
"%PY%" scripts\studio.py %*
if errorlevel 1 pause
