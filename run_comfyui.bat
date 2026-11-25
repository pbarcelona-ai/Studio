@echo off
rem Start local ComfyUI server on 127.0.0.1:8188 for Pistachio's Studio (RTX 5090 CUDA)
cd /d "%~dp0.local_ai\ComfyUI"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ComfyUI environment not found at .local_ai\ComfyUI\.venv
  pause
  exit /b 1
)
"%PY%" main.py --listen 127.0.0.1 --port 8188 %*
if errorlevel 1 pause
