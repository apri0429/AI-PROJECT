from __future__ import annotations

from pathlib import Path
from typing import Any


def list_files(folder_id: str | None = None) -> list[dict[str, Any]]:
    return [] if not folder_id else [{"id": folder_id, "name": "example-folder"}]


def download_file(file_id: str, destination: str | Path) -> str:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text("placeholder", encoding="utf-8")
    return str(destination_path)
