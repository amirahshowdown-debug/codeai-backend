@echo off
cd /d %~dp0
if not exist venv python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo Edit backend\.env and add your Gemini API key, then run this file again.
pause
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
