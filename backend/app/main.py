from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo
from pathlib import Path

from .config import settings
from .db_init import ensure_schema
from .pages import router as pages_router
from .ingest import router as ingest_router
from .retention import run_retention

app = FastAPI(title="Face Attendance (PG)")

# serve /static (css/js)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# serve /storage (snapshots/enroll tmp if needed)
STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

@app.middleware("http")
async def force_https_redirect(request, call_next):
    # Redirect only when users access via LAN HTTP endpoint
    # Keep localhost/127.0.0.1 traffic untouched for worker/backend local calls.
    host = (request.url.hostname or "").lower()
    if request.url.scheme == "http" and host == "172.18.36.46":
        target = f"https://172.18.36.46:8443{request.url.path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(url=target, status_code=307)
    return await call_next(request)

@app.on_event("startup")
def _startup():
    ensure_schema()

    # scheduler: daily at 02:00 Thai time
    sched = BackgroundScheduler(timezone=ZoneInfo(settings.TZ))
    sched.add_job(run_retention, "cron", hour=2, minute=0, second=0, id="retention", replace_existing=True)
    sched.start()
    app.state.scheduler = sched

@app.on_event("shutdown")
def _shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown(wait=False)

app.include_router(pages_router)
app.include_router(ingest_router)

@app.get("/health")
def health():
    return {"ok": True}
