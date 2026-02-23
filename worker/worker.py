import os
import time
import json
from datetime import datetime, timezone
from urllib.parse import quote

import cv2
import numpy as np
import requests
from dotenv import load_dotenv

from embedder import make_embedder

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

BACKEND = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("WORKER_API_KEY", "")
CAMERA_NAME = os.getenv("CAMERA_NAME", "ENTRY_GATE_1")

CAM_HOST = os.getenv("CAMERA_HOST")
CAM_USER = os.getenv("CAMERA_USER")
CAM_PASS = os.getenv("CAMERA_PASS")
CH = os.getenv("RTSP_CHANNEL", "102")

FPS_PROCESS = int(os.getenv("FPS_PROCESS", "5"))

# ROI crop (optional). If ROI_X2/ROI_Y2 are 0 => disabled.
ROI_X1 = int(os.getenv("ROI_X1", "0"))
ROI_Y1 = int(os.getenv("ROI_Y1", "0"))
ROI_X2 = int(os.getenv("ROI_X2", "0"))
ROI_Y2 = int(os.getenv("ROI_Y2", "0"))

def build_rtsp_url():
    u = quote(CAM_USER or "", safe="")
    p = quote(CAM_PASS or "", safe="")
    return f"rtsp://{u}:{p}@{CAM_HOST}:554/Streaming/Channels/{CH}"

def crop_roi(frame: np.ndarray) -> np.ndarray:
    if ROI_X2 <= 0 or ROI_Y2 <= 0:
        return frame
    h, w = frame.shape[:2]
    x1 = max(0, min(w-1, ROI_X1))
    y1 = max(0, min(h-1, ROI_Y1))
    x2 = max(1, min(w, ROI_X2))
    y2 = max(1, min(h, ROI_Y2))
    if x2 <= x1 or y2 <= y1:
        return frame
    return frame[y1:y2, x1:x2]

def pick_best(face_list):
    # pick best by quality, then largest area
    best = None
    best_key = None
    for f in face_list:
        x1,y1,x2,y2 = f["bbox"]
        area = (x2-x1)*(y2-y1)
        key = (f["quality"], area)
        if best is None or key > best_key:
            best, best_key = f, key
    return best

def send_to_backend(event_ts: str, embedding: np.ndarray, jpeg_bytes: bytes):
    if not API_KEY:
        raise RuntimeError("WORKER_API_KEY is empty. Check D:\\face_attendance_pg\\.env")

    files = {"frame": ("frame.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "camera_name": CAMERA_NAME,
        "event_ts_utc": event_ts,
        "embedding_json": json.dumps(embedding.astype(float).tolist()),
    }

    headers = {
        "X-API-Key": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
    }

    r = requests.post(
        f"{BACKEND.rstrip('/')}/api/ingest/frame",
        data=data,
        files=files,
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

def main():
    if not all([CAM_HOST, CAM_USER, CAM_PASS]):
        raise RuntimeError("Missing CAMERA_HOST/CAMERA_USER/CAMERA_PASS in .env")

    rtsp = build_rtsp_url()
    print(f"[worker] RTSP = {rtsp}  (credentials url-encoded)")

    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise RuntimeError("Cannot open RTSP stream. Check credentials/network.")

    embedder = make_embedder()
    print(f"[worker] Embedder = {embedder.__class__.__name__}")

    frame_interval = 1.0 / max(1, FPS_PROCESS)
    last_proc = 0.0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(1)
            cap.release()
            cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
            continue

        now = time.time()
        if now - last_proc < frame_interval:
            continue
        last_proc = now

        frame = crop_roi(frame)

        faces = embedder.detect_and_embed(frame)
        if not faces:
            continue

        best = pick_best(faces)
        if best is None:
            continue

        # minimal quality gate (tune later)
        if best["quality"] < 0.15:
            continue

        emb = best["embedding"]

        # encode frame as jpeg for proof snapshot (backend will only keep it for first check-in)
        ok2, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok2:
            continue

        event_ts = datetime.now(timezone.utc).isoformat()

        try:
            resp = send_to_backend(event_ts, emb, buf.tobytes())
            if resp.get("status") == "known":
                print(f"[worker] known: {resp.get('match_employee_id')} score={resp.get('match_score')}")
        except Exception as e:
            print(f"[worker] send error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
