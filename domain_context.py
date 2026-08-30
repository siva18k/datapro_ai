"""In-memory domain packs for Ask / Analytics (bindings + reference texts)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from catalog_db import get_domain, list_domains
from mcp_domain_service import domain_mcp_capabilities, load_domain_reference_resources

_CAP_TYPES = ("tool", "resource", "prompt")

_packs: dict[str, "DomainContextPack"] = {}
_lock = Lock()


@dataclass
class DomainContextPack:
    domain_id: str
    slug: str
    name: str
    bindings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    reference_texts: dict[str, dict[str, Any]] = field(default_factory=dict)
    warmed_at: str = ""

    @property
    def has_bindings(self) -> bool:
        return any(self.bindings.get(cap) for cap in _CAP_TYPES)


def clear_domain_context(domain_id: str | None = None) -> None:
    global _packs
    with _lock:
        if domain_id:
            _packs.pop(str(domain_id), None)
            return
        _packs.clear()


def _load_bindings(domain_id: str) -> dict[str, list[dict[str, Any]]]:
    return {cap_type: domain_mcp_capabilities(domain_id, cap_type) for cap_type in _CAP_TYPES}


def _load_reference_texts(
    domain_id: str,
    domain_slug: str | None,
    bindings: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    if not bindings.get("resource"):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for kind in ("sql", "rag"):
        for item in load_domain_reference_resources(
            domain_id, domain_slug=domain_slug, execution_kind=kind
        ):
            key = item.get("reference_key")
            if key and key not in out:
                out[str(key)] = item
    return out


def get_domain_context(domain_id: str | None) -> DomainContextPack | None:
    """Return a warmed pack for this domain (built once until catalog invalidation)."""
    if not domain_id:
        return None
    key = str(domain_id)
    with _lock:
        cached = _packs.get(key)
        if cached is not None:
            return cached

        domain = get_domain(domain_id=domain_id)
        if not domain:
            return None

        bindings = _load_bindings(domain_id)
        slug = domain.get("slug")
        pack = DomainContextPack(
            domain_id=key,
            slug=slug or "",
            name=domain.get("name") or slug or "",
            bindings=bindings,
            reference_texts=_load_reference_texts(domain_id, slug, bindings),
            warmed_at=datetime.now(timezone.utc).isoformat(),
        )
        _packs[key] = pack
        return pack


def reference_resources_for(
    pack: DomainContextPack,
    execution_kind: str,
) -> list[dict[str, Any]]:
    from mcp_reference_service import reference_uris_for_execution

    out: list[dict[str, Any]] = []
    for key in reference_uris_for_execution(execution_kind):
        item = pack.reference_texts.get(key)
        if item:
            out.append(dict(item))
    return out


def warm_domain_context() -> int:
    """Preload packs for every catalog domain. Returns how many were warmed."""
    count = 0
    for domain in list_domains():
        if get_domain_context(domain.get("id")):
            count += 1
    return count
