from __future__ import annotations

from typing import Any


def calculate_dieline(width: Any, height: Any) -> dict[str, float]:
    try:
        width_value = float(width)
        height_value = float(height)
    except (TypeError, ValueError):
        return {"width": 0.0, "height": 0.0, "bleed": 0.0}

    return {
        "width": width_value,
        "height": height_value,
        "bleed": round(max(width_value, height_value) * 0.02, 2),
    }
