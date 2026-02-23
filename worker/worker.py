import os
import time
import json
from dataclasses import dataclass
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
WORKER_NAME = os.getenv("WORKER_NAME", os.getenv("COMPUTERNAME", "worker"))

FPS_PROCESS_DEFAULT = int(os.getenv("FPS_PROCESS", "5"))
HEARTBEAT_SECONDS = int(os.getenv("WORKER_HEARTBEAT_SECONDS", "15"))
HEARTBEAT_PREVIEW_SECONDS = int(os.getenv("WORKER_HEARTBEAT_PREVIEW_SECONDS", "60"))


@dataclass
class CameraConfig:
    name: str
    host: str | None
    user: str | None
    password: str | None
    channel: str
    fps_process: int
    roi_x1: int = 0
    roi_y1: int = 0
    roi_x2: int = 0
    roi_y2: int = 0
    rtsp_url: str | None = None


@dataclass
class CameraRuntime:
    cfg: CameraConfig
    cap: cv2.VideoCapture | None = None
    last_proc: float = 0.0
    last_heartbeat: float = 0.0
    last_preview: float = 0.0
    last_error: str | None = None


def build_rtsp_url(cfg: CameraConfig) -> str:
    if cfg.rtsp_url:
        return cfg.rtsp_url
    u = quote(cfg.user or "", safe="")
    p = quote(cfg.password or "", safe="")
    return f"rtsp://{u}:{p}@{cfg.host}:554/Streaming/Channels/{cfg.channel}"


def _parse_cameras() -> list[CameraConfig]:
    """
    รองรับ 2 แบบ:
    1) CAMERA_CONFIGS เป็น JSON array
    2) single camera แบบเดิม (CAMERA_*)
    """
    raw = os.getenv("CAMERA_CONFIGS", "").strip()
    cams: list[CameraConfig] = []

    if raw:
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                for i, c in enumerate(arr, start=1):
                    if not isinstance(c, dict):
                        continue
                    cams.append(
                        CameraConfig(
                            name=str(c.get("name") or f"CAM_{i}"),
                            host=c.get("host"),
                            user=c.get("user"),
                            password=c.get("password"),
                            channel=str(c.get("channel") or "102"),
                            fps_process=int(c.get("fps_process") or FPS_PROCESS_DEFAULT),
                            roi_x1=int(c.get("roi_x1") or 0),
                            roi_y1=int(c.get("roi_y1") or 0),
                            roi_x2=int(c.get("roi_x2") or 0),
                            roi_y2=int(c.get("roi_y2") or 0),
                            rtsp_url=c.get("rtsp_url"),
                        )
                    )
        except Exception as e:
            print(f"[worker] CAMERA_CONFIGS parse error: {e}")

    if cams:
        return cams

    # backward-compatible single camera from old env
    cams.append(
        CameraConfig(
            name=os.getenv("CAMERA_NAME", "ENTRY_GATE_1"),
            host=os.getenv("CAMERA_HOST"),
            user=os.getenv("CAMERA_USER"),
            password=os.getenv("CAMERA_PASS"),
            channel=os.getenv("RTSP_CHANNEL", "102"),
            fps_process=FPS_PROCESS_DEFAULT,
            roi_x1=int(os.getenv("ROI_X1", "0")),
            roi_y1=int(os.getenv("ROI_Y1", "0")),
            roi_x2=int(os.getenv("ROI_X2", "0")),
            roi_y2=int(os.getenv("ROI_Y2", "0")),
            rtsp_url=os.getenv("CAMERA_RTSP", "") or None,
        )
    )
    return cams


def crop_roi(frame: np.ndarray, cfg: CameraConfig) -> np.ndarray:
    if cfg.roi_x2 <= 0 or cfg.roi_y2 <= 0:
        return frame
    h, w = frame.shape[:2]
    x1 = max(0, min(w - 1, cfg.roi_x1))
    y1 = max(0, min(h - 1, cfg.roi_y1))
    x2 = max(1, min(w, cfg.roi_x2))
    y2 = max(1, min(h, cfg.roi_y2))
    if x2 <= x1 or y2 <= y1:
        return frame
    return frame[y1:y2, x1:x2]


def pick_best(face_list):
    best = None
    best_key = None
    for f in face_list:
        x1, y1, x2, y2 = f["bbox"]
        area = (x2 - x1) * (y2 - y1)
        key = (f["quality"], area)
        if best is None or key > best_key:
            best, best_key = f, key
    return best


def _auth_headers() -> dict:
    if not API_KEY:
        raise RuntimeError("WORKER_API_KEY is empty. Check D:\\face_attendance_pg\\.env")
    return {"X-API-Key": API_KEY, "Authorization": f"Bearer {API_KEY}"}


def send_to_backend(camera_name: str, event_ts: str, embedding: np.ndarray, jpeg_bytes: bytes):
    files = {"frame": ("frame.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "camera_name": camera_name,
        "event_ts_utc": event_ts,
        "embedding_json": json.dumps(embedding.astype(float).tolist()),
    }

    r = requests.post(
        f"{BACKEND.rstrip('/')}/api/ingest/frame",
        data=data,
        files=files,
        headers=_auth_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def send_heartbeat(camera_name: str, status: str, error_text: str | None = None, preview_jpeg: bytes | None = None):
    data = {
        "camera_name": camera_name,
        "status": status,
        "event_ts_utc": datetime.now(timezone.utc).isoformat(),
        "worker_name": WORKER_NAME,
        "last_error": (error_text or "")[:500],
    }
    files = None
    if preview_jpeg:
        files = {"preview": ("preview.jpg", preview_jpeg, "image/jpeg")}

    r = requests.post(
        f"{BACKEND.rstrip('/')}/api/ingest/worker-heartbeat",
        data=data,
        files=files,
        headers=_auth_headers(),
        timeout=10,
    )
    r.raise_for_status()


def _open_camera(rt: CameraRuntime):
    rtsp = build_rtsp_url(rt.cfg)
    if rt.cap is not None:
        try:
            rt.cap.release()
        except Exception:
            pass
    rt.cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    if rt.cap.isOpened():
        rt.last_error = None
        print(f"[worker] camera={rt.cfg.name} connected")
    else:
        rt.last_error = "Cannot open RTSP stream"
        print(f"[worker] camera={rt.cfg.name} open failed")


def main():
    cameras = _parse_cameras()
    if not cameras:
        raise RuntimeError("No camera config found")

    # validate basic config
    for c in cameras:
        if not c.rtsp_url and not all([c.host, c.user, c.password]):
            raise RuntimeError(f"Missing camera config for {c.name}")

    runtimes = [CameraRuntime(cfg=c) for c in cameras]
    for rt in runtimes:
        _open_camera(rt)

    embedder = make_embedder()
    print(f"[worker] Embedder = {embedder.__class__.__name__}")
    print(f"[worker] Cameras = {[r.cfg.name for r in runtimes]}")

    while True:
        now = time.time()
        for rt in runtimes:
            cfg = rt.cfg

            # reconnect if needed
            if rt.cap is None or (not rt.cap.isOpened()):
                _open_camera(rt)
                if now - rt.last_heartbeat >= HEARTBEAT_SECONDS:
                    try:
                        send_heartbeat(cfg.name, "offline", rt.last_error)
                    except Exception as e:
                        print(f"[worker] heartbeat error ({cfg.name}): {e}")
                    rt.last_heartbeat = now
                time.sleep(0.05)
                continue

            ok, frame = rt.cap.read()
            if not ok or frame is None:
                rt.last_error = "Read frame failed"
                try:
                    rt.cap.release()
                except Exception:
                    pass
                rt.cap = None
                if now - rt.last_heartbeat >= HEARTBEAT_SECONDS:
                    try:
                        send_heartbeat(cfg.name, "offline", rt.last_error)
                    except Exception as e:
                        print(f"[worker] heartbeat error ({cfg.name}): {e}")
                    rt.last_heartbeat = now
                continue

            # online heartbeat (with preview every N sec)
            if now - rt.last_heartbeat >= HEARTBEAT_SECONDS:
                preview_bytes = None
                if now - rt.last_preview >= HEARTBEAT_PREVIEW_SECONDS:
                    okp, bufp = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if okp:
                        preview_bytes = bufp.tobytes()
                        rt.last_preview = now
                try:
                    send_heartbeat(cfg.name, "online", None, preview_bytes)
                except Exception as e:
                    print(f"[worker] heartbeat error ({cfg.name}): {e}")
                rt.last_heartbeat = now

            # process by fps
            frame_interval = 1.0 / max(1, cfg.fps_process)
            if now - rt.last_proc < frame_interval:
                continue
            rt.last_proc = now

            frame_proc = crop_roi(frame, cfg)
            faces = embedder.detect_and_embed(frame_proc)
            if not faces:
                continue

            best = pick_best(faces)
            if best is None or best["quality"] < 0.15:
                continue

            emb = best["embedding"]
            ok2, buf = cv2.imencode(".jpg", frame_proc, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok2:
                continue

            event_ts = datetime.now(timezone.utc).isoformat()
            try:
                resp = send_to_backend(cfg.name, event_ts, emb, buf.tobytes())
                if resp.get("status") == "known":
                    print(f"[worker] {cfg.name} known: {resp.get('match_employee_id')} score={resp.get('match_score')}")
            except Exception as e:
                print(f"[worker] send error ({cfg.name}): {e}")

        time.sleep(0.01)


if __name__ == "__main__":
    main()
