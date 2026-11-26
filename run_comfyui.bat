@echo off
rem Start local ComfyUI server on 127.0.0.1:8188 for Pistachio's Studio (RTX 5090 CUDA)
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%ROOT%.local_ai\ComfyUI\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Python environment not found for ComfyUI.
  pause
  exit /b 1
)
set "PYTHONPATH=%ROOT%.local_ai\ComfyUI\.venv\Lib\site-packages;%ROOT%.venv\Lib\site-packages"
cd /d "%ROOT%.local_ai\ComfyUI"
start "Pistachio ComfyUI (RTX 5090)" "%PY%" -X utf8 main.py --listen 127.0.0.1 --port 8188 %*
exit /b 0
