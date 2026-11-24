"""Connector registry and plugin loading.

A *connector* turns an :class:`~opentearsheet.models.Entity` into a
:class:`~opentearsheet.models.Section` of cited facts and exportable rows.

Add one in this repo with the ``@register`` decorator, or ship one in your own
package and expose it through the ``opentearsheet.connectors`` entry-point group
(see CONTRIBUTING.md). Installed plugins are discovered automatically.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from .models import Entity, Section

ENTRY_POINT_GROUP = "opentearsheet.connectors"


class BaseConnector:
    name: str = ""            # unique id, e.g. "form4"
    title: str = ""           # shown as a memo heading / UI tab
    entity_kinds: tuple[str, ...] = ()
    experimental: bool = False
    order: int = 100          # lower runs (and displays) first

    def applies(self, entity: Entity) -> bool:
        return entity.kind in self.entity_kinds

    def run(self, client: Any, entity: Entity, options: dict[str, Any]) -> Section:
        raise NotImplementedError


_REGISTRY: dict[str, Any] = {}


def register(obj):
    """Register a connector class or instance. Usable as a class decorator."""
    instance = obj() if isinstance(obj, type) else obj
    if not getattr(instance, "name", ""):
        raise ValueError("A connector must define a non-empty `name`")
    if not callable(getattr(instance, "run", None)) or not callable(getattr(instance, "applies", None)):
        raise TypeError(f"Connector {instance.name!r} must implement applies() and run()")
    _REGISTRY[instance.name] = instance
    return obj


def unregister(name: str) -> None:
    _REGISTRY.pop(name, None)


def all_connectors() -> list:
    return sorted(_REGISTRY.values(), key=lambda c: (getattr(c, "order", 100), c.name))


def connectors_for(entity: Entity) -> list:
    return [c for c in all_connectors() if c.applies(entity)]


def load_builtin() -> None:
    from . import connectors  # noqa: F401  (modules register themselves on import)


def load_plugins(group: str = ENTRY_POINT_GROUP) -> list[str]:
    """Load third-party connectors. Returns error messages instead of raising."""
    errors = []
    for ep in entry_points(group=group):
        try:
            register(ep.load())
        except Exception as exc:  # a broken plugin must never take the app down
            errors.append(f"{ep.name}: {exc}")
    return errors
