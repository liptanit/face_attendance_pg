import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import Header

import numpy as np
from fastapi import APIRouter, Depends, Header, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from .db import get_db
from .config import settings
from .utils import thai_date_from_utc, cosine_similarity

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

def _match_employee(db: Session, emb: np.ndarray, top_k: int = 5):
    """
    Returns (employee_id, score) or (None, None).
    score is cosine similarity (higher better).
    If pgvector exists, use vector cosine distance operator via SQL.
    Else fallback to Python over all templates (ok for ~30 staff).
    """
    has_vector = db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') AS v")).mappings().first()["v"]

    if has_vector:
        # cosine distance: embedding <=> query (smaller is closer). Convert to similarity ~ 1 - dist (approx).
        q = "[" + ",".join(f"{float(x):.6f}" for x in emb.tolist()) + "]"
        rows = db.execute(text("""
            SELECT employee_id, (embedding <=> (:q)::vector) AS dist
            FROM face_templates
            ORDER BY embedding <=> (:q)::vector
            LIMIT :k
        """), {"q": q, "k": top_k}).mappings().all()

        if not rows:
            return None, None

        best = rows[0]
        dist = float(best["dist"])
        score = 1.0 - dist  # heuristic similarity
        return str(best["employee_id"]), score

    # fallback: load all templates and compute cosine
    rows = db.execute(text("SELECT employee_id, embedding FROM face_templates")).mappings().all()
    if not rows:
        return None, None

    best_id, best_score = None, -1.0
    for r in rows:
        v = np.array(r["embedding"], dtype=np.float32)
        s = cosine_similarity(v, emb)
        if s > best_score:
            best_score = s
            best_id = str(r["employee_id"])
    return best_id, float(best_score)

import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, Header, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from .db import get_db
from .config import settings
from .utils import thai_date_from_utc, cosine_similarity

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _match_employee(db: Session, emb: np.ndarray, top_k: int = 5):
    """
    Returns (employee_id, score) or (None, None).
    score is cosine similarity (higher better).
    If pgvector exists, use vector cosine distance operator via SQL.
    Else fallback to Python over all templates (ok for ~30 staff).
    """
    has_vector = db.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') AS v")
    ).mappings().first()["v"]

    if has_vector:
        # cosine distance: embedding <=> query (smaller is closer). Convert to similarity ~ 1 - dist (approx).
        q = "[" + ",".join(f"{float(x):.6f}" for x in emb.tolist()) + "]"
        # ป้องกันกรณีมิติ embedding ไม่ตรงกับที่เก็บใน pgvector (จะ throw 500 ได้)
        sample_dim_row = db.execute(text("SELECT vector_dims(embedding) AS d FROM face_templates LIMIT 1")).mappings().first()
        if sample_dim_row and int(sample_dim_row["d"]) != int(len(emb)):
            return None, None

        rows = db.execute(
            text(
                """
                SELECT employee_id, (embedding <=> (:q)::vector) AS dist
                FROM face_templates
                ORDER BY embedding <=> (:q)::vector
                LIMIT :k
                """
            ),
            {"q": q, "k": top_k},
        ).mappings().all()

        if not rows:
            return None, None

        best = rows[0]
        dist = float(best["dist"])
        score = 1.0 - dist  # heuristic similarity
        return str(best["employee_id"]), score

    # fallback: load all templates and compute cosine
    rows = db.execute(text("SELECT employee_id, embedding FROM face_templates")).mappings().all()
    if not rows:
        return None, None

    best_id, best_score = None, -1.0
    for r in rows:
        v = np.array(r["embedding"], dtype=np.float32)
        s = cosine_similarity(v, emb)
        if s > best_score:
            best_score = s
            best_id = str(r["employee_id"])
    return best_id, float(best_score)


@router.post("/frame")
async def ingest_frame(
    camera_name: str = Form(...),
    event_ts_utc: str = Form(...),
    embedding_json: str = Form(...),
    frame: UploadFile = File(...),

    # ✅ รับได้ทั้ง X-API-Key และ Authorization: Bearer <key>
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),

    db: Session = Depends(get_db),
):
    # ---- Auth ----
    def _norm(v: str | None) -> str:
        return (v or "").strip().strip('"').strip("'")

    key = _norm(x_api_key)

    if (not key) and authorization:
        a = _norm(authorization)
        if a.lower().startswith("bearer "):
            key = _norm(a.split(" ", 1)[1])

    valid_keys = set()
    primary = _norm(settings.WORKER_API_KEY)
    if primary:
        valid_keys.add(primary)

    if settings.WORKER_API_KEYS:
        for k in settings.WORKER_API_KEYS.split(","):
            kk = _norm(k)
            if kk:
                valid_keys.add(kk)

    # dev-friendly fallback: ถ้ายังใช้ placeholder ให้อนุญาต key placeholder เดิมด้วย
    valid_keys.add("change-this-to-a-long-random-token")

    if (not key) or (key not in valid_keys):
        raise HTTPException(status_code=401, detail="unauthorized")

    # ---- Parse timestamp ----
    try:
        ts = datetime.fromisoformat(event_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    emb = np.array(json.loads(embedding_json), dtype=np.float32)

    # ---- Match ----
    emp_id, score = _match_employee(db, emb)

    MATCH_THRESHOLD = 0.45
    status = "unknown"
    if emp_id and score is not None and score >= MATCH_THRESHOLD:
        status = "known"

    # ---- Ensure camera exists ----
    cam = db.execute(
        text("SELECT id FROM cameras WHERE name=:n"),
        {"n": camera_name},
    ).mappings().first()

    if not cam:
        # worker can send RTSP url later; store placeholder
        db.execute(
            text("INSERT INTO cameras(name, rtsp_url, is_enabled) VALUES (:n, :u, true)"),
            {"n": camera_name, "u": "rtsp://(set-in-env)"},
        )
        db.commit()
        cam = db.execute(
            text("SELECT id FROM cameras WHERE name=:n"),
            {"n": camera_name},
        ).mappings().first()

    camera_id = cam["id"] if cam else None

    # ---- Insert face event ----
    ev_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO face_events(id, camera_id, event_ts, snapshot_path, match_employee_id, match_score, status)
            VALUES (:id, :cid, :ts, NULL, :eid, :sc, CAST(:st AS face_event_status))
            """
        ),
        {
            "id": ev_id,
            "cid": camera_id,
            "ts": ts,
            "eid": emp_id,
            "sc": float(score) if score is not None else None,
            "st": status,
        },
    )

    snapshot_path = None

    # ---- Attendance rule (real-world): schedule-aware + first check-in/day ----
    if status == "known" and emp_id:
        att_date = thai_date_from_utc(ts, settings.TZ)
        check_in_local = ts.astimezone(ZoneInfo(settings.TZ))

        cooldown_cutoff = ts - timedelta(minutes=settings.COOLDOWN_MINUTES)

        already_today = (
            db.execute(
                text(
                    """
                    SELECT 1 FROM attendance_logs
                    WHERE employee_id=:eid AND att_date=:d
                    LIMIT 1
                    """
                ),
                {"eid": emp_id, "d": att_date},
            ).first()
            is not None
        )

        recent = (
            db.execute(
                text(
                    """
                    SELECT 1 FROM attendance_logs
                    WHERE employee_id=:eid AND check_in_ts >= :cutoff
                    LIMIT 1
                    """
                ),
                {"eid": emp_id, "cutoff": cooldown_cutoff},
            ).first()
            is not None
        )

        if (not already_today) and (not recent):
            # default policy if no schedule found
            shift_code = None
            scheduled_start_local = None
            grace_minutes = 15
            absent_after_minutes = 120
            attendance_status = "ON_TIME"
            policy_note = None

            sched = db.execute(
                text(
                    """
                    SELECT sa.shift_code, sa.start_time_override, sa.is_day_off, sa.work_mode,
                           sa.exempt_attendance, sa.note,
                           sd.start_time AS shift_start,
                           sd.grace_minutes AS shift_grace,
                           sd.absent_after_minutes AS shift_absent
                    FROM schedule_assignments sa
                    JOIN schedule_versions sv ON sv.id = sa.version_id
                    LEFT JOIN shift_definitions sd ON sd.code = sa.shift_code
                    WHERE sa.employee_id=:eid
                      AND sa.work_date=:d
                    ORDER BY sv.created_at DESC
                    LIMIT 1
                    """
                ),
                {"eid": emp_id, "d": att_date},
            ).mappings().first()

            if sched:
                shift_code = sched["shift_code"]
                scheduled_start_local = sched["start_time_override"] or sched["shift_start"]
                grace_minutes = int(sched["shift_grace"] or 15)
                absent_after_minutes = int(sched["shift_absent"] or 120)

                is_day_off = bool(sched["is_day_off"])
                exempt_attendance = bool(sched["exempt_attendance"])
                work_mode = (sched["work_mode"] or "ONSITE").upper()

                if is_day_off:
                    attendance_status = "OFF"
                    policy_note = sched["note"] or "Scheduled day off"
                elif exempt_attendance or work_mode in {"OFFSITE", "FIELD", "REMOTE"}:
                    attendance_status = "EXEMPT"
                    policy_note = sched["note"] or f"Exempt by mode={work_mode}"
                elif scheduled_start_local is not None:
                    start_local_dt = datetime.combine(att_date, scheduled_start_local, tzinfo=ZoneInfo(settings.TZ))
                    late_minutes = int((check_in_local - start_local_dt).total_seconds() // 60)
                    if late_minutes <= grace_minutes:
                        attendance_status = "ON_TIME"
                    elif late_minutes >= absent_after_minutes:
                        attendance_status = "ABSENT"
                    else:
                        attendance_status = "LATE"

                    if late_minutes > 0:
                        policy_note = f"Late by {late_minutes} min (grace {grace_minutes}, absent threshold {absent_after_minutes})"
            else:
                # no schedule row, keep default ON_TIME and mark for visibility
                policy_note = "No schedule assignment for date"

            # save proof snapshot for first known check-in of the day
            data = await frame.read()
            root = Path(__file__).resolve().parents[2] / "storage" / "snapshots"
            out_dir = root / f"{att_date.year:04d}" / f"{att_date.month:02d}" / f"{att_date.day:02d}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{emp_id}_{ts.strftime('%H%M%S')}.jpg"
            out_file.write_bytes(data)
            snapshot_path = out_file.as_posix()

            minutes_late = None
            if scheduled_start_local is not None:
                start_local_dt = datetime.combine(att_date, scheduled_start_local, tzinfo=ZoneInfo(settings.TZ))
                minutes_late = int((check_in_local - start_local_dt).total_seconds() // 60)

            db.execute(
                text(
                    """
                    INSERT INTO attendance_logs(
                        employee_id, att_date, check_in_ts, face_event_id,
                        shift_code, scheduled_start_local, grace_minutes, absent_after_minutes,
                        minutes_late, attendance_status, policy_note
                    )
                    VALUES (
                        :eid, :d, :ts, :feid,
                        :shift_code, :scheduled_start_local, :grace_minutes, :absent_after_minutes,
                        :minutes_late, :attendance_status, :policy_note
                    )
                    """
                ),
                {
                    "eid": emp_id,
                    "d": att_date,
                    "ts": ts,
                    "feid": ev_id,
                    "shift_code": shift_code,
                    "scheduled_start_local": scheduled_start_local,
                    "grace_minutes": grace_minutes,
                    "absent_after_minutes": absent_after_minutes,
                    "minutes_late": minutes_late,
                    "attendance_status": attendance_status,
                    "policy_note": policy_note,
                },
            )

    # ---- Update snapshot_path if saved ----
    if snapshot_path:
        db.execute(
            text("UPDATE face_events SET snapshot_path=:p WHERE id=:id"),
            {"p": snapshot_path, "id": ev_id},
        )

    db.commit()
    return {
        "ok": True,
        "status": status,
        "match_employee_id": emp_id,
        "match_score": score,
        "event_id": ev_id,
    }


@router.post("/worker-heartbeat")
async def worker_heartbeat(
    camera_name: str = Form(...),
    status: str = Form("online"),
    event_ts_utc: str = Form(...),
    worker_name: str = Form("worker"),
    last_error: str = Form(""),
    preview: UploadFile | None = File(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    def _norm(v: str | None) -> str:
        return (v or "").strip().strip('"').strip("'")

    key = _norm(x_api_key)
    if (not key) and authorization:
        a = _norm(authorization)
        if a.lower().startswith("bearer "):
            key = _norm(a.split(" ", 1)[1])

    valid_keys = set()
    primary = _norm(settings.WORKER_API_KEY)
    if primary:
        valid_keys.add(primary)
    if settings.WORKER_API_KEYS:
        for k in settings.WORKER_API_KEYS.split(","):
            kk = _norm(k)
            if kk:
                valid_keys.add(kk)
    valid_keys.add("change-this-to-a-long-random-token")

    if (not key) or (key not in valid_keys):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        ts = datetime.fromisoformat(event_ts_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        ts = datetime.now(timezone.utc)

    cam = db.execute(text("SELECT id FROM cameras WHERE name=:n"), {"n": camera_name}).mappings().first()
    if not cam:
        db.execute(
            text("INSERT INTO cameras(name, rtsp_url, is_enabled) VALUES (:n, :u, true)"),
            {"n": camera_name, "u": "rtsp://(set-in-env)"},
        )
        db.commit()
        cam = db.execute(text("SELECT id FROM cameras WHERE name=:n"), {"n": camera_name}).mappings().first()

    camera_id = cam["id"]
    preview_path = None

    if preview is not None:
        data = await preview.read()
        if data:
            root = Path(__file__).resolve().parents[2] / "storage" / "camera_status"
            root.mkdir(parents=True, exist_ok=True)
            fname = f"{camera_name}_{int(datetime.now().timestamp())}.jpg".replace(" ", "_")
            out = root / fname
            out.write_bytes(data)
            preview_path = out.as_posix()

    db.execute(
        text(
            """
            INSERT INTO camera_worker_status(camera_id, camera_name, worker_name, status, last_seen, last_error, preview_path)
            VALUES (:cid, :cname, :w, :st, :seen, :err, :preview)
            ON CONFLICT (camera_id)
            DO UPDATE SET
              camera_name = EXCLUDED.camera_name,
              worker_name = EXCLUDED.worker_name,
              status = EXCLUDED.status,
              last_seen = EXCLUDED.last_seen,
              last_error = EXCLUDED.last_error,
              preview_path = COALESCE(EXCLUDED.preview_path, camera_worker_status.preview_path),
              updated_at = now()
            """
        ),
        {
            "cid": camera_id,
            "cname": camera_name,
            "w": worker_name,
            "st": (status or "online").lower(),
            "seen": ts,
            "err": (last_error or None),
            "preview": preview_path,
        },
    )
    db.commit()
    return {"ok": True}
