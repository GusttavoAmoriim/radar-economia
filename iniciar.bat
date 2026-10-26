@echo off
cd /d "%~dp0"
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt)
.venv\Scripts\python coletor.py coletar
.venv\Scripts\python coletor.py painel
pause
