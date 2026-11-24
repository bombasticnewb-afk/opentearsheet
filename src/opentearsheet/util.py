"""Small formatting and safety helpers."""

from __future__ import annotations

import json
from typing import Any, Optional

# Spreadsheet apps execute cells that start with these characters (CSV/formula injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def fmt_usd(value: Optional[float], signed: bool = False) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    a = abs(value)
    for div, suffix, places in ((1e9, "B", 2), (1e6, "M", 2), (1e3, "K", 1)):
        if a >= div:
            return f"{sign}${a / div:,.{places}f}{suffix}"
    return f"{sign}${a:,.0f}"


def fmt_num(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def maybe_json(value: Any) -> dict:
    """IAPD returns some nested objects as JSON strings; accept either form."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def first_of(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def md_escape(text: str) -> str:
    """Escape characters that would break a Markdown link label."""
    return str(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
