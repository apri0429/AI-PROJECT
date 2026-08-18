from __future__ import annotations

from typing import Any

from models import ValidationIssue


def validate_rows(rows: list[dict[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_fields = {"vendor_name", "product_name"}

    for index, row in enumerate(rows, start=2):
        for field in required_fields:
            value = row.get(field, "")
            if not str(value).strip():
                issues.append(ValidationIssue(field=field, message=f"Row {index} is missing {field}", severity="error"))

        if row.get("vendor_name") and row.get("product_name") and str(row.get("vendor_name")).lower() == str(row.get("product_name")).lower():
            issues.append(ValidationIssue(field="vendor_name", message=f"Row {index} has suspicious duplicate vendor/product values", severity="warning"))

    return issues
