@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python "%~dp0launch.py"
) else (
    py -3 "%~dp0launch.py"
)
if errorlevel 1 pause
