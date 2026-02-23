from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import text
from .db import engine
from .config import settings

def run_retention():
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)
    # Find old events with snapshots
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, snapshot_path FROM face_events
            WHERE event_ts < :cutoff AND snapshot_path IS NOT NULL
        """), {"cutoff": cutoff}).mappings().all()

        # Delete files
        for r in rows:
            p = r["snapshot_path"]
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass

        # Delete old face_events (attendance_logs references face_event_id with ON DELETE SET NULL)
        conn.execute(text("DELETE FROM face_events WHERE event_ts < :cutoff"), {"cutoff": cutoff})
