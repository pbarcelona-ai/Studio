@echo off
rem One-time setup for Pistachio's Studio on Windows: double-click this file. It runs install.ps1 (PowerShell) for this folder only.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
