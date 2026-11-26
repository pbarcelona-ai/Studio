@echo off
rem Start Pistachio's Studio on Windows (double-click this file, or run it in a terminal). It opens the page in your browser.
rem install.bat makes .venv with everything the Studio needs. Press Ctrl+C in the Studio window to stop immediately (no Y/N batch prompt).
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "STUDIO_PAUSE_ON_ERROR=1"
if not exist "%PY%" (
  echo The Studio is not installed yet: double-click install.bat first.
  pause
  exit /b 1
)
rem Launch Python directly in its own console window so cmd.exe exits immediately and never prompts "Terminate batch job (Y/N)?" on Ctrl+C.
start "Pistachio's Studio" "%PY%" -X utf8 scripts\studio.py %*
exit /b 0
