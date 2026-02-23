from pathlib import Path
import re

p = Path(r"D:\face_attendance_pg\backend\app\pages.py")
s = p.read_text(encoding="utf-8")
pattern = r'@router\.get\("/dashboard/monthly", response_class=HTMLResponse\)\ndef dashboard_monthly\([\s\S]*?\n\s*\}\)\n?$'
new_func = '''@router.get("/dashboard/monthly", response_class=HTMLResponse)
def dashboard_monthly(request: Request, month: str | None = None, db: Session = Depends(get_db)):
    redir = require_login(request)
    if redir:
        return redir

    if month:
        try:
            month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
        except Exception:
            month_start = date.today().replace(day=1)
    else:
        month_start = date.today().replace(day=1)

    now_local = datetime.now(ZoneInfo(settings.TZ))
    today_local = now_local.date()

    kpi = db.execute(text("""
        SELECT
          COALESCE(SUM(CASE WHEN attendance_status='LATE' THEN 1 ELSE 0 END),0) AS total_late,
          COALESCE(SUM(CASE WHEN attendance_status='ABSENT' THEN 1 ELSE 0 END),0) AS total_absent,
          COALESCE(SUM(CASE WHEN attendance_status='EXEMPT' THEN 1 ELSE 0 END),0) AS total_exempt,
          COALESCE(SUM(CASE WHEN attendance_status='ON_TIME' THEN 1 ELSE 0 END),0) AS total_on_time,
          COALESCE(SUM(CASE WHEN attendance_status='OFF' THEN 1 ELSE 0 END),0) AS total_off
        FROM attendance_logs
        WHERE date_trunc('month', att_date)::date = :m
    """), {"m": month_start}).mappings().first()

    top_late = db.execute(text("""
        SELECT e.emp_code, e.full_name, COUNT(*)::int AS late_count
        FROM attendance_logs a
        JOIN employees e ON e.id=a.employee_id
        WHERE date_trunc('month', a.att_date)::date=:m AND a.attendance_status='LATE'
        GROUP BY e.emp_code, e.full_name
        ORDER BY late_count DESC, e.emp_code
        LIMIT 10
    """), {"m": month_start}).mappings().all()

    top_absent = db.execute(text("""
        SELECT e.emp_code, e.full_name, COUNT(*)::int AS absent_count
        FROM attendance_logs a
        JOIN employees e ON e.id=a.employee_id
        WHERE date_trunc('month', a.att_date)::date=:m AND a.attendance_status='ABSENT'
        GROUP BY e.emp_code, e.full_name
        ORDER BY absent_count DESC, e.emp_code
        LIMIT 10
    """), {"m": month_start}).mappings().all()

    live_rows = db.execute(
        text(
            """
            WITH latest_version AS (
              SELECT id
              FROM schedule_versions
              WHERE month_start = date_trunc('month', :today::date)::date
              ORDER BY created_at DESC
              LIMIT 1
            )
            SELECT
              COALESCE(sa.shift_code, '-') AS shift_code,
              e.emp_code,
              e.full_name,
              COALESCE(sa.start_time_override, sd.start_time) AS shift_start,
              COALESCE(a.attendance_status,
                CASE
                  WHEN sa.is_day_off THEN 'OFF'
                  WHEN sa.exempt_attendance OR UPPER(COALESCE(sa.work_mode,'ONSITE')) IN ('OFFSITE','REMOTE','FIELD') THEN 'EXEMPT'
                  ELSE 'PENDING'
                END
              ) AS live_status,
              COALESCE(a.minutes_late, 0) AS minutes_late,
              (a.check_in_ts AT TIME ZONE 'Asia/Bangkok') AS check_in_local
            FROM schedule_assignments sa
            JOIN latest_version lv ON lv.id = sa.version_id
            JOIN employees e ON e.id = sa.employee_id AND e.is_active = true
            LEFT JOIN shift_definitions sd ON sd.code = sa.shift_code
            LEFT JOIN attendance_logs a ON a.employee_id = sa.employee_id AND a.att_date = sa.work_date
            WHERE sa.work_date = :today
              AND COALESCE(sa.start_time_override, sd.start_time) IS NOT NULL
              AND :now_local >= (:today::timestamp + COALESCE(sa.start_time_override, sd.start_time))
              AND :now_local < ((:today::timestamp + COALESCE(sa.start_time_override, sd.start_time)) + interval '9 hour')
            ORDER BY sa.shift_code, e.emp_code
            """
        ),
        {"today": today_local, "now_local": now_local.replace(tzinfo=None)},
    ).mappings().all()

    live_by_shift = {}
    live_summary = {"ON_TIME": 0, "LATE": 0, "ABSENT": 0, "EXEMPT": 0, "OFF": 0, "PENDING": 0}
    for r in live_rows:
        d = dict(r)
        sc = d.get("shift_code") or "-"
        live_by_shift.setdefault(sc, []).append(d)
        st = (d.get("live_status") or "PENDING").upper()
        if st not in live_summary:
            live_summary[st] = 0
        live_summary[st] += 1

    return templates.TemplateResponse("dashboard_monthly.html", {
        "request": request,
        "month": month_start.strftime("%Y-%m"),
        "kpi": kpi,
        "top_late": top_late,
        "top_absent": top_absent,
        "live_by_shift": live_by_shift,
        "live_summary": live_summary,
        "now_local": now_local,
    })
'''

ns, n = re.subn(pattern, new_func, s, count=1)
if n != 1:
    raise SystemExit(f"pattern not matched: {n}")

p.write_text(ns, encoding="utf-8")
print("patched")
