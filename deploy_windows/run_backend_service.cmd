@echo off
setlocal
set INSIGHTFACE_HOME=D:\face_attendance_models

cd /d D:\face_attendance_pg\backend
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
