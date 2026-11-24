"""Namespace-agnostic XML helpers for SEC documents.

Uses defusedxml when installed (it is in requirements.txt); otherwise falls back to the
standard library parser, which never resolves external entities.
"""

from __future__ import annotations

from typing import Optional
from xml.etree.ElementTree import Element

try:
    from defusedxml.ElementTree import fromstring as _fromstring  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised only without defusedxml
    from xml.etree.ElementTree import fromstring as _fromstring


def parse_xml(data: bytes) -> Element:
    root = _fromstring(data)
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def text(el: Optional[Element], path: str) -> Optional[str]:
    """Text at ``path``. Form 4 wraps most values in a ``<value>`` child; unwrap it."""
    if el is None:
        return None
    node = el.find(path)
    if node is None:
        return None
    inner = node.find("value")
    if inner is not None:
        node = inner
    result = (node.text or "").strip()
    return result or None


def num(el: Optional[Element], path: str) -> Optional[float]:
    raw = text(el, path)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def flag(el: Optional[Element], path: str) -> bool:
    return (text(el, path) or "").lower() in {"1", "true", "y", "yes"}
