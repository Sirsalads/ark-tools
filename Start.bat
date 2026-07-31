@echo off
rem  A.N.S Tools — double-click this.
rem
rem  Nothing has to be installed first. The bootstrap finds a Python if the
rem  machine has one, installs a private copy inside this folder if it does not,
rem  puts the packages in .venv, and opens the app. Only the first run is slow.
title A.N.S Tools

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup.ps1" -Launch
if errorlevel 1 (
    echo.
    echo   Setup did not finish. The lines above say why.
    echo.
    pause
)
