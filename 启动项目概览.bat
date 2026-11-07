@echo off
cd /d "%~dp0backend"
start "Project Overview" http://127.0.0.1:18765/
python -m uvicorn app:app --host 127.0.0.1 --port 18765
pause

