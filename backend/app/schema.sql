-- Extensions (uuid + optional vector)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
  WHEN others THEN
    -- pgvector not installed; continue
    RAISE NOTICE 'pgvector extension not available, continuing without it';
END
$$;

-- Employees
CREATE TABLE IF NOT EXISTS employees (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  emp_code text UNIQUE NOT NULL,
  full_name text NOT NULL,
  department text,
  is_active boolean NOT NULL DEFAULT true,
  deleted_at timestamptz,
  deleted_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS deleted_by text;

-- Cameras
CREATE TABLE IF NOT EXISTS cameras (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text UNIQUE NOT NULL,
  rtsp_url text NOT NULL,
  location text,
  is_enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Face templates: try vector(512) if pgvector exists, else float4[]
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN
    EXECUTE 'CREATE TABLE IF NOT EXISTS face_templates (
      id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
      employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
      embedding vector(512) NOT NULL,
      quality_score real NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    )';
  ELSE
    EXECUTE 'CREATE TABLE IF NOT EXISTS face_templates (
      id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
      employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
      embedding float4[] NOT NULL,
      quality_score real NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    )';
  END IF;
END
$$;

-- Face event status enum
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'face_event_status') THEN
    CREATE TYPE face_event_status AS ENUM ('known','unknown','low_quality');
  END IF;
END
$$;

-- Face events
CREATE TABLE IF NOT EXISTS face_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  camera_id uuid REFERENCES cameras(id) ON DELETE SET NULL,
  event_ts timestamptz NOT NULL DEFAULT now(),
  snapshot_path text,
  match_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  match_score real,
  status face_event_status NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Attendance: 1 person/day
CREATE TABLE IF NOT EXISTS attendance_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  att_date date NOT NULL,
  check_in_ts timestamptz NOT NULL,
  face_event_id uuid REFERENCES face_events(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_attendance_once_per_day UNIQUE (employee_id, att_date)
);

-- Audit logs
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor text NOT NULL,
  action text NOT NULL,
  entity text NOT NULL,
  entity_id uuid,
  detail jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_face_events_ts ON face_events(event_ts);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_logs(att_date);

-- Worker camera heartbeat status (for monitoring page)
CREATE TABLE IF NOT EXISTS camera_worker_status (
  camera_id uuid PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
  camera_name text NOT NULL,
  worker_name text,
  status text NOT NULL DEFAULT 'offline',
  last_seen timestamptz,
  last_error text,
  preview_path text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_camera_worker_status_last_seen ON camera_worker_status(last_seen);

-- Shift definitions (editable)
CREATE TABLE IF NOT EXISTS shift_definitions (
  code text PRIMARY KEY,
  name text,
  start_time time NOT NULL,
  grace_minutes int NOT NULL DEFAULT 15,
  absent_after_minutes int NOT NULL DEFAULT 120,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO shift_definitions(code, name, start_time, grace_minutes, absent_after_minutes, is_active)
VALUES
  ('A','Shift A','06:00',15,120,true),
  ('N','Shift N','09:00',15,120,true),
  ('B','Shift B','13:00',15,120,true),
  ('C','Shift C','21:30',15,120,true)
ON CONFLICT (code) DO NOTHING;

-- Schedule versions + assignments
CREATE TABLE IF NOT EXISTS schedule_versions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  month_start date NOT NULL,
  source text NOT NULL DEFAULT 'excel',
  uploaded_by text,
  file_name text,
  file_sha256 text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'excel';
ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS uploaded_by text;
ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS file_name text;
ALTER TABLE schedule_versions ADD COLUMN IF NOT EXISTS file_sha256 text;
CREATE INDEX IF NOT EXISTS idx_schedule_versions_month ON schedule_versions(month_start);

CREATE TABLE IF NOT EXISTS schedule_assignments (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  version_id uuid NOT NULL REFERENCES schedule_versions(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  work_date date NOT NULL,
  shift_code text,
  start_time_override time,
  is_day_off boolean NOT NULL DEFAULT false,
  work_mode text NOT NULL DEFAULT 'ONSITE', -- ONSITE/OFFSITE/HYBRID
  exempt_attendance boolean NOT NULL DEFAULT false,
  note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_schedule_assignment UNIQUE (version_id, employee_id, work_date)
);

ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS start_time_override time;
ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS is_day_off boolean NOT NULL DEFAULT false;
ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS work_mode text NOT NULL DEFAULT 'ONSITE';
ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS exempt_attendance boolean NOT NULL DEFAULT false;
ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS note text;
ALTER TABLE schedule_assignments ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_schedule_assignments_emp_date ON schedule_assignments(employee_id, work_date);

-- Enrich attendance logs for real-world policy
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS shift_code text;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS scheduled_start_local time;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS grace_minutes int;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS absent_after_minutes int;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS minutes_late int;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS attendance_status text; -- ON_TIME/LATE/ABSENT/EXEMPT/OFF
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS policy_note text;

-- Vector index if possible
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN
    BEGIN
      EXECUTE 'CREATE INDEX IF NOT EXISTS idx_face_templates_embedding
               ON face_templates USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)';
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'Could not create ivfflat index (maybe missing opclass or pgvector version). Continue.';
    END;
  END IF;
END
$$;
