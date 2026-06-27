from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

SourceType = Literal["structured", "unstructured"]
SchemaContextKind = Literal["sql", "python", "none"]


@dataclass(frozen=True)
class ConnectorAsset:
    id: str
    name: str
    kind: str
    size_bytes: int | None = None
    synced: bool = False
    meta: dict[str, Any] | None = None


@dataclass
class SyncResult:
    assets_added: list[str] = field(default_factory=list)
    assets_updated: list[str] = field(default_factory=list)
    assets_removed: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    cache_path: str | None = None


class DatasetConnector(Protocol):
    connector_type: str
    source_type: SourceType

    def normalize_config(self, config: dict | None) -> dict: ...

    def test_connection(self, source: dict) -> tuple[bool, str]: ...

    def list_assets(self, source: dict) -> list[ConnectorAsset]: ...

    def sync(
        self,
        source: dict,
        *,
        asset_ids: list[str] | None = None,
        full: bool = False,
    ) -> SyncResult: ...

    def schema_context_kind(self, source: dict) -> SchemaContextKind: ...

    def build_schema_context(self, source: dict) -> dict[str, Any]: ...
