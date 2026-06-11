"""JSON-safe coercion for API responses (SQL rows, etc.)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


def coerce_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def coerce_json_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [[coerce_json_value(cell) for cell in row] for row in rows]
