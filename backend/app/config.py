from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]  # ...\backend
ROOT_DIR = Path(__file__).resolve().parents[2]  # ...\face_attendance_pg


class Settings(BaseSettings):
    # IMPORTANT:
    # เราอนุญาตให้ .env มี key อื่นๆ (ของ worker/camera) ได้ โดยไม่ทำให้ backend crash
    model_config = SettingsConfigDict(
        # รองรับทั้ง root/.env และ backend/.env โดยให้ root/.env มีสิทธิ์ override ค่า
        env_file=(BASE_DIR / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",          # ✅ หัวใจของปัญหา: ignore ตัวแปรที่ backend ไม่ได้ใช้
        case_sensitive=False,
    )

    # ---- Core / Auth ----
    SECRET_KEY: str = Field(default="change-me-please")
    ADMIN_USER: str = Field(default="admin")
    ADMIN_PASS: str = Field(default="Admin@CC")

    # ---- Database ----
    # รองรับได้ทั้ง DSN และแบบแยก fields
    PG_DSN: str | None = Field(default=None)
    PG_HOST: str = Field(default="127.0.0.1")
    PG_PORT: int = Field(default=5432)
    PG_DB: str = Field(default="face_attendance")
    PG_USER: str = Field(default="postgres")
    PG_PASSWORD: str = Field(default="postgres")

    # ---- App Timezone / Behavior ----
    TZ: str = Field(default="Asia/Bangkok")
    COOLDOWN_MINUTES: int = Field(default=15)
    RETENTION_DAYS: int = Field(default=14)

    # ---- Worker Auth ----
    WORKER_API_KEY: str = Field(default="change-worker-key")
    # Optional: comma-separated keys for key rotation, e.g. "key1,key2"
    WORKER_API_KEYS: str | None = Field(default=None)

    # ---- Optional toggles ----
    DEBUG: bool = Field(default=False)

    # ---- Optional default schedule template file ----
    SCHEDULE_TEMPLATE_PATH: str = Field(default=r"P:\Document\Admin\Schedule\2026\02\02_Feb_2026.xlsx")


    @property
    def database_url(self) -> str:
        # ถ้ามี PG_DSN ให้ใช้ก่อน
        if self.PG_DSN:
            return self.PG_DSN

        # ไม่ใช้ URL object เพื่อลดปัญหา encode รหัสผ่านที่มีอักขระพิเศษ
        user = quote_plus(self.PG_USER)
        password = quote_plus(self.PG_PASSWORD)
        host = self.PG_HOST
        port = self.PG_PORT
        db = self.PG_DB
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


settings = Settings()
