from __future__ import annotations

from dataset_connectors.base import ConnectorAsset, SyncResult
from structured_db import list_schema_tables, postgres_config_from_source, test_postgres_connection


class PostgresConnector:
    connector_type = "postgres"
    source_type = "structured"

    def normalize_config(self, config: dict | None) -> dict:
        cfg = dict(config or {})
        cfg.setdefault("schema", "public")
        cfg.setdefault("port", 5432)
        return cfg

    def test_connection(self, source: dict) -> tuple[bool, str]:
        cfg = postgres_config_from_source(source)
        return test_postgres_connection(cfg)

    def list_assets(self, source: dict) -> list[ConnectorAsset]:
        try:
            tables = list_schema_tables(postgres_config_from_source(source))
        except Exception as exc:
            return [
                ConnectorAsset(
                    id="__error__",
                    name=str(exc),
                    kind="error",
                    synced=False,
                )
            ]
        schema = (source.get("config") or {}).get("schema") or "public"
        return [
            ConnectorAsset(
                id=name,
                name=f"{schema}.{name}",
                kind="table",
                synced=True,
            )
            for name in tables
        ]

    def sync(
        self,
        source: dict,
        *,
        asset_ids: list[str] | None = None,
        full: bool = False,
    ) -> SyncResult:
        """Postgres datasets sync via catalog table discovery — no file cache."""
        assets = self.list_assets(source)
        if assets and assets[0].kind == "error":
            return SyncResult(errors=[{"error": assets[0].name}])
        names = [a.id for a in assets if a.kind == "table"]
        if asset_ids:
            names = [n for n in names if n in asset_ids]
        return SyncResult(assets_updated=names)

    def schema_context_kind(self, source: dict) -> str:
        return "sql"

    def build_schema_context(self, source: dict) -> dict:
        from structured_orchestrator import build_schema_context

        ctx = build_schema_context(source["id"])
        return {
            "kind": "sql",
            "source_id": ctx.source_id,
            "source_name": ctx.source_name,
            "domain_name": ctx.domain_name,
            "tables": ctx.tables,
            "prompt_block": ctx.to_llm_prompt_block(),
        }
