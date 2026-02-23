from pathlib import Path
from sqlalchemy import text
from .db import engine

def ensure_schema():
    sql_path = Path(__file__).with_name("schema.sql")
    sql = sql_path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        # Execute as a single batch
        conn.execute(text(sql))
