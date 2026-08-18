from __future__ import annotations

from core.validator import validate_rows


def test_validate_rows_detects_missing_required_fields() -> None:
    rows = [{"vendor_name": "", "product_name": ""}]
    issues = validate_rows(rows)
    assert any(issue.field == "vendor_name" and issue.severity == "error" for issue in issues)
    assert any(issue.field == "product_name" and issue.severity == "error" for issue in issues)
