"""Plain data types shared by connectors, the memo builder and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Source:
    """A public document a fact was taken from."""

    label: str
    url: str


@dataclass
class Fact:
    """One verifiable statement. ``id`` (F1, F2, ...) is assigned when the memo is built."""

    key: str
    text: str
    value: Any = None
    sources: list[Source] = field(default_factory=list)
    id: str = ""


@dataclass
class Section:
    """Output of one connector: facts for the memo plus rows for CSV export."""

    connector: str
    title: str
    facts: list[Fact] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    columns: Optional[list[str]] = None


@dataclass
class Entity:
    """What is being researched.

    ``kind`` is "company" (an issuer, looked up by ticker/CIK) or "firm"
    (an investment manager: 13F filer CIK and/or IAPD CRD number).
    """

    kind: str
    name: str
    cik: Optional[str] = None
    ticker: Optional[str] = None
    crd: Optional[str] = None

    @property
    def display(self) -> str:
        ids = [x for x in (self.ticker, f"CIK {self.cik}" if self.cik else None, f"CRD {self.crd}" if self.crd else None) if x]
        return f"{self.name} ({' · '.join(ids)})" if ids else self.name
