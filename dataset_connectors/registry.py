from __future__ import annotations

from typing import Any

from dataset_connectors.base import DatasetConnector
from dataset_connectors.file import ApiConnector, FilePathConnector, SharePointConnector, UploadConnector, WebUrlConnector
from dataset_connectors.postgres import PostgresConnector
from dataset_connectors.trino import TrinoConnector

CONNECTOR_SOURCE_TYPES: dict[str, str] = {
    "trino": "structured",
    "postgres": "structured",
    "upload": "unstructured",
    "file_path": "unstructured",
    "api": "unstructured",
    "sharepoint": "unstructured",
    "web_url": "unstructured",
}

CONTENT_CONNECTORS: tuple[str, ...] = (
    "upload",
    "file_path",
    "api",
    "web_url",
    "sharepoint",
)

REMOTE_CONNECTORS: tuple[str, ...] = ("api", "web_url", "sharepoint")

_REGISTRY: dict[str, DatasetConnector] = {
    "trino": TrinoConnector(),
    "postgres": PostgresConnector(),
    "upload": UploadConnector(),
    "file_path": FilePathConnector(),
    "api": ApiConnector(),
    "web_url": WebUrlConnector(),
    "sharepoint": SharePointConnector(),
}


def get_connector(connector: str) -> DatasetConnector:
    adapter = _REGISTRY.get(connector)
    if not adapter:
        raise ValueError(f"Unknown connector: {connector}")
    return adapter


def get_connector_for_source(source: dict) -> DatasetConnector:
    return get_connector(source["connector"])


def is_content_connector(connector: str) -> bool:
    return connector in CONTENT_CONNECTORS


def is_remote_connector(connector: str) -> bool:
    return connector in REMOTE_CONNECTORS


def connector_source_type(connector: str) -> str:
    return CONNECTOR_SOURCE_TYPES.get(connector, "unstructured")


def asset_to_dict(asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "name": asset.name,
        "kind": asset.kind,
        "size_bytes": asset.size_bytes,
        "synced": asset.synced,
        "meta": asset.meta or {},
    }


def sync_result_to_dict(result) -> dict[str, Any]:
    return {
        "assets_added": result.assets_added,
        "assets_updated": result.assets_updated,
        "assets_removed": result.assets_removed,
        "errors": result.errors,
        "cache_path": result.cache_path,
    }
