from __future__ import annotations

from typing import Any


def update_master_sheet(row: dict[str, Any]) -> dict[str, Any]:
    return {"updated": True, "row": row}
