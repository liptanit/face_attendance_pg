# Face Attendance (PostgreSQL) — 1 Camera, Check-in Only, Proof Snapshot 14 Days

**Dev:** Windows 11  
**Prod:** Windows Server 2022  
**No Docker**

## What you get
- FastAPI backend + simple Admin UI (Jinja templates)
- Employee management + Webcam enrollment (capture 15–25 images)
- RTSP worker (OpenCV) + modular face embedder (InsightFace optional)
- PostgreSQL schema + optional pgvector for fast vector search
- Attendance rule: **check-in only** (1 person/day) + cooldown
- Store proof snapshots **only for successful check-in (known)**, auto-delete older than **RETENTION_DAYS** (default 14)

## 1) Prereqs
- Python 3.10+ (3.11 recommended for best wheels)
- PostgreSQL 15/16 installed locally
- (Recommended) pgvector extension installed in PostgreSQL

> Notes:
> - Your camera password contains special chars like `@`. The worker URL-encodes it automatically.
> - If you use InsightFace pretrained models, review model/license suitability for your use (especially commercial).

## 2) Setup Postgres
Create user and database:
```sql
CREATE USER faceapp WITH PASSWORD 'YOUR_STRONG_PASSWORD';
CREATE DATABASE face_attendance OWNER faceapp;
```

If pgvector is installed:
```sql
\c face_attendance
CREATE EXTENSION IF NOT EXISTS vector;
```

## 3) Configure env
Copy `.env.example` to `.env` and fill values:
- PG_* (db connection)
- ADMIN_USER/ADMIN_PASS
- WORKER_API_KEY (long random token)
- CAMERA_* (credentials)
- Optional ROI_* (crop area), 0 means "no ROI crop"

## 4) Install & run backend
```bat
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:
- http://127.0.0.1:8000/login

Backend auto-initializes tables on first run (and attempts to `CREATE EXTENSION vector;` if available).

## 5) Install & run worker (RTSP)
```bat
cd worker
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py worker.py
```

### Enable real face recognition
By default, the worker uses a `DummyEmbedder` (no recognition).
To enable recognition, install InsightFace + onnxruntime:
```bat
pip install insightface onnxruntime opencv-python
```
Then set:
```env
EMBEDDER=insightface
```
Worker will use InsightFace FaceAnalysis to detect+embed.

## 6) Enrollment (webcam)
- Go to Employees -> Add employee
- Click Enroll -> allow webcam
- Capture 15–25 images (various angles)
- Finalize Enrollment

## 7) Attendance
- When a known employee is detected, the backend creates:
  - face_event (status=known)
  - attendance_log (if first check-in of that Thai date)
  - proof snapshot file **only for first check-in**

## 8) Troubleshooting
- If RTSP opens in VLC but not in worker: often password special chars; URL-encoding is already used. Ensure `.env` is correct.
- If `CREATE EXTENSION vector` fails: pgvector not installed. System still runs; matching will fallback to Python similarity in backend.

