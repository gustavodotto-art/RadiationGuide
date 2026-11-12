@echo off
cd /d "%~dp0"
title Radiation Guide 2.0.0-rc1 - Teste
where py >nul 2>nul
if errorlevel 1 goto use_python
for %%V in (3.12 3.13 3.11 3.10) do (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        py -%%V INICIAR.py
        goto finish
    )
)
:use_python
python INICIAR.py
:finish
if errorlevel 1 pause
