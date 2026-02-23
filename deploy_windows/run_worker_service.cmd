@echo off
setlocal
set INSIGHTFACE_HOME=D:\face_attendance_models

cd /d D:\face_attendance_pg\worker
call .venv\Scripts\activate.bat
python worker.py
