from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    workspace_dir: str = os.getenv("WORKSPACE_DIR", str(BASE_DIR))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    gemini_image_model: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    google_drive_folder_id: str | None = os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None
    docs_destination_folder_id: str | None = os.getenv("DOCS_DESTINATION_FOLDER_ID") or None
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "vendor_sheet_ai")
    sheet_sync_interval_seconds: int = int(os.getenv("SHEET_SYNC_INTERVAL_SECONDS", "300"))
    google_sheets_api_key: str | None = os.getenv("GOOGLE_SHEETS_API_KEY") or None


settings = Settings()
