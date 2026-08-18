from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str = "warning"


@dataclass
class NormalizedSheet:
    headers: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None


@dataclass
class PipelineResult:
    file_name: str
    normalized_rows: list[dict[str, Any]]
    issues: list[ValidationIssue] = field(default_factory=list)
    status: str = "ok"
