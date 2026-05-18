"""Shared finding/severity types used by all checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning", "info"]
_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    file: str | None = None
    hint: str | None = None

    def sort_key(self) -> tuple[int, str, str]:
        return (_ORDER[self.severity], self.file or "", self.code)
