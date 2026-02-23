# Face Attendance (PG) - Full Project

This package includes:
- backend (FastAPI + Admin UI)
- worker (RTSP recognition worker)
- deploy_windows (Caddy + NSSM service scripts)

## Quick start (Dev)
1) Start backend:
   cd backend
   .venv\Scripts\activate
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

2) Open:
   http://localhost:8000/login

## Production style (HTTPS via IP)
Goal:
- Users access: https://172.18.36.46:8443/login
- Backend binds to: 127.0.0.1:8000
- Worker calls backend via localhost
- Services run as LocalSystem

### Steps
1) Copy deploy_windows\Caddyfile -> C:\Caddy\Caddyfile
2) Ensure C:\Caddy\caddy.exe exists
3) Ensure C:\NSSM\nssm.exe exists
4) Run as Administrator:
   D:\face_attendance_pg\deploy_windows\install_services.cmd

### Trust Caddy internal CA on client machines (optional but recommended)
Copy:
C:\Windows\System32\config\systemprofile\AppData\Roaming\Caddy\pki\authorities\local\root.crt
to client, then run (Admin):
certutil -addstore -f "Root" root.crt

## Important
Because services run as LocalSystem, InsightFace models should be stored in:
D:\face_attendance_models
The scripts set:
INSIGHTFACE_HOME=D:\face_attendance_models
