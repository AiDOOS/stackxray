@echo off
setlocal
title StackXray - Agentify Opportunities

rem Run from this launcher's own folder (so it finds API-KEY.txt and saves the report here).
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"

rem Find Python: prefer the 'py' launcher, then 'python' on PATH.
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE ( where python >nul 2>nul && set "PYEXE=python" )
if not defined PYEXE (
  echo.
  echo   Python was not found on this computer.
  echo   Please install Python 3.11 or newer from https://www.python.org/downloads
  echo   IMPORTANT: on the first install screen, tick "Add Python to PATH".
  echo   Then run StackXray again.
  echo.
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo    StackXray  -  find your best "make it an AI agent" chances
echo    A window will open in your browser. Type the folder to scan.
echo    Keep THIS window open while you use it. Close it to stop.
echo   ============================================================
echo.
%PYEXE% -m stackxray
pause
