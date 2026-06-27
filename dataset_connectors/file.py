from __future__ import annotations

from pathlib import Path

from catalog_service import get_source_data_path, list_source_files
from dataset_connectors.base import ConnectorAsset, SyncResult
from ingest_service import SUPPORTED_EXTENSIONS


class UploadConnector:
    connector_type = "upload"
    source_type = "unstructured"

    def normalize_config(self, config: dict | None) -> dict:
        return dict(config or {})

    def test_connection(self, source: dict) -> tuple[bool, str]:
        path = get_source_data_path(source)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            return False, f"Cannot write to dataset folder: {exc}"
        return True, f"Upload folder ready: {path}"

    def list_assets(self, source: dict) -> list[ConnectorAsset]:
        assets: list[ConnectorAsset] = []
        for path in list_source_files(source):
            assets.append(
                ConnectorAsset(
                    id=path.name,
                    name=path.name,
                    kind="file",
                    size_bytes=path.stat().st_size,
                    synced=True,
                )
            )
        return assets

    def sync(
        self,
        source: dict,
        *,
        asset_ids: list[str] | None = None,
        full: bool = False,
    ) -> SyncResult:
        path = get_source_data_path(source)
        names = [a.name for a in self.list_assets(source)]
        return SyncResult(
            assets_added=[],
            assets_updated=names,
            cache_path=str(path),
        )

    def schema_context_kind(self, source: dict) -> str:
        return "python"

    def build_schema_context(self, source: dict) -> dict:
        from code_orchestrator import build_file_dataset_context

        ctx = build_file_dataset_context(source["id"])
        return {
            "kind": "python",
            "source_id": ctx.source_id,
            "source_name": ctx.source_name,
            "domain_name": ctx.domain_name,
            "data_dir": ctx.data_dir,
            "files": ctx.files,
            "prompt_block": ctx.to_llm_prompt_block(),
        }


class FilePathConnector(UploadConnector):
    connector_type = "file_path"

    def test_connection(self, source: dict) -> tuple[bool, str]:
        path = get_source_data_path(source)
        if not path.exists():
            return False, f"Folder not found: {path}"
        if not path.is_dir():
            return False, f"Path is not a directory: {path}"
        return True, f"Folder readable: {path}"


class RemoteCacheConnector:
    """Base for connectors that fetch remote content into the dataset cache folder."""

    source_type = "unstructured"

    def normalize_config(self, config: dict | None) -> dict:
        return dict(config or {})

    def _cache_path(self, source: dict) -> Path:
        return get_source_data_path(source)

    def _remote_pairs(self, config: dict) -> list[tuple[str, str]]:
        raise NotImplementedError

    def test_connection(self, source: dict) -> tuple[bool, str]:
        cfg = source.get("config") or {}
        pairs = self._remote_pairs(cfg)
        if not pairs:
            return False, "No URL configured"
        headers = self._headers(cfg)
        from dataset_connectors.http_utils import fetch_url

        asset_id, url = pairs[0]
        try:
            fetch_url(url, headers=headers)
        except Exception as exc:
            return False, f"Cannot reach {url}: {exc}"
        return True, f"Reachable ({len(pairs)} endpoint(s) configured)"

    def _headers(self, config: dict) -> dict[str, str]:
        from dataset_connectors.http_utils import build_request_headers

        return build_request_headers(config)

    def list_assets(self, source: dict) -> list[ConnectorAsset]:
        cfg = source.get("config") or {}
        cached = {p.name: p for p in list_source_files(source)}
        assets: list[ConnectorAsset] = []
        for asset_id, url in self._remote_pairs(cfg):
            match = cached.get(safe_cached_name(asset_id, url, cached))
            for path in cached.values():
                if path.stem == asset_id or path.name.startswith(f"{asset_id}."):
                    match = path
                    break
            assets.append(
                ConnectorAsset(
                    id=asset_id,
                    name=url,
                    kind="remote",
                    size_bytes=match.stat().st_size if match else None,
                    synced=match is not None,
                    meta={"url": url},
                )
            )
        for path in cached.values():
            if not any(a.synced and path.name.startswith(a.id) for a in assets):
                assets.append(
                    ConnectorAsset(
                        id=path.name,
                        name=path.name,
                        kind="file",
                        size_bytes=path.stat().st_size,
                        synced=True,
                    )
                )
        return assets

    def sync(
        self,
        source: dict,
        *,
        asset_ids: list[str] | None = None,
        full: bool = False,
    ) -> SyncResult:
        from dataset_connectors.http_utils import fetch_url, materialize_bytes

        cfg = source.get("config") or {}
        dest = self._cache_path(source)
        headers = self._headers(cfg)
        result = SyncResult(cache_path=str(dest))
        pairs = self._remote_pairs(cfg)
        if not pairs:
            result.errors.append({"error": "No URL configured — save a web link on the Connection tab first."})
            return result
        if asset_ids:
            allowed = set(asset_ids)
            pairs = [(aid, url) for aid, url in pairs if aid in allowed]
        if full:
            for path in list(dest.iterdir()) if dest.exists() else []:
                if path.is_file():
                    path.unlink()
                    result.assets_removed.append(path.name)

        for asset_id, url in pairs:
            try:
                content, content_type = fetch_url(url, headers=headers)
                target = materialize_bytes(dest, asset_id, url, content, content_type)
                if target.name in result.assets_removed:
                    result.assets_removed.remove(target.name)
                    result.assets_updated.append(target.name)
                elif target.exists() and target.stat().st_size:
                    result.assets_updated.append(target.name)
                else:
                    result.assets_added.append(target.name)
            except Exception as exc:
                result.errors.append({"asset_id": asset_id, "url": url, "error": str(exc)})
        return result

    def schema_context_kind(self, source: dict) -> str:
        return "python"

    def build_schema_context(self, source: dict) -> dict:
        from code_orchestrator import build_file_dataset_context

        ctx = build_file_dataset_context(source["id"])
        return {
            "kind": "python",
            "source_id": ctx.source_id,
            "source_name": ctx.source_name,
            "domain_name": ctx.domain_name,
            "data_dir": ctx.data_dir,
            "files": ctx.files,
            "prompt_block": ctx.to_llm_prompt_block(),
        }


def safe_cached_name(asset_id: str, url: str, cached: dict[str, Path]) -> str:
    for name in cached:
        if name.startswith(f"{asset_id}."):
            return name
    return asset_id


class WebUrlConnector(RemoteCacheConnector):
    connector_type = "web_url"

    def _remote_pairs(self, config: dict) -> list[tuple[str, str]]:
        from dataset_connectors.http_utils import configured_urls

        return configured_urls(config)


class SharePointConnector(RemoteCacheConnector):
    connector_type = "sharepoint"

    def _remote_pairs(self, config: dict) -> list[tuple[str, str]]:
        from dataset_connectors.http_utils import configured_urls

        return configured_urls(config)


class ApiConnector(RemoteCacheConnector):
    connector_type = "api"

    def _remote_pairs(self, config: dict) -> list[tuple[str, str]]:
        from dataset_connectors.http_utils import configured_api_endpoints

        return configured_api_endpoints(config)
