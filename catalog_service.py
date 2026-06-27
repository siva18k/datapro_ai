"""High-level catalog operations: paths, ingest, domain context."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from catalog_db import (
    bulk_update_source_file_rag,
    bulk_update_table_rag,
    create_domain,
    create_source,
    delete_source,
    get_domain,
    get_rag_profile,
    get_source,
    init_catalog,
    list_domains,
    list_source_file_rag,
    list_sources,
    update_rag_profile,
    update_source,
    upsert_source_file_rag,
)
from db import delete_chunks_by_source, delete_chunks_for_source, list_ingested_sources, upsert_chunks
from ingest_service import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SUPPORTED_EXTENSIONS,
    build_items_for_file,
    chunk_text,
    ingest_files,
    list_available_docs,
)

PROJECT_DIR = Path(__file__).resolve().parent


def ensure_catalog_ready() -> None:
    """Ensure migrations and seed data exist."""
    init_catalog()


def _default_source_data_rel_path(source: dict) -> str:
    domain_slug = source.get("domain_slug") or "general"
    source_slug = source.get("slug") or "dataset"
    return f"data/{domain_slug}/{source_slug}"


def _uses_legacy_sample_docs(source: dict, path: str | None) -> bool:
    """True only for seeded datasets that intentionally share sample_docs/."""
    if path != "sample_docs":
        return False
    slug = source.get("slug") or ""
    connector = source.get("connector") or ""
    return connector == "file_path" and slug in ("sample_docs", "hr_policies")


def get_source_data_path(source: dict, *, repair_config: bool = True) -> Path:
    cfg = dict(source.get("config") or {})
    path = cfg.get("path")
    if not path or (path == "sample_docs" and not _uses_legacy_sample_docs(source, path)):
        path = _default_source_data_rel_path(source)
        if repair_config and source.get("id") and cfg.get("path") != path:
            cfg["path"] = path
            update_source(source["id"], config=cfg)
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = PROJECT_DIR / resolved
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def get_dataset_definition_path(source: dict) -> Path:
    """Filesystem path for the dataset definition markdown file."""
    domain_slug = source.get("domain_slug") or "general"
    source_slug = source.get("slug") or "dataset"
    path = PROJECT_DIR / "data" / domain_slug / source_slug / "definition.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_dataset_definition(source: dict) -> str:
    cfg = source.get("config") or {}
    if cfg.get("definition_md"):
        return cfg["definition_md"]
    path = get_dataset_definition_path(source)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _default_definition_template(source)


def save_dataset_definition(source: dict, markdown: str) -> None:
    markdown = markdown.strip()
    path = get_dataset_definition_path(source)
    path.write_text(markdown + "\n", encoding="utf-8")
    cfg = dict(source.get("config") or {})
    cfg["definition_md"] = markdown
    cfg["definition_path"] = str(path.relative_to(PROJECT_DIR))
    update_source(source["id"], config=cfg)


def _default_definition_template(source: dict) -> str:
    connector = source.get("connector", "upload")
    return f"""# {source.get('name', 'Dataset')}

## Overview
Brief description of what this dataset contains and who uses it.

## Type
{connector}

## Purpose
Why this dataset exists in the catalog.

## Contents
- Key entities, tables, or document types

## Usage notes
How analysts and AI should use this data.

## Update cadence
How often the data is refreshed.
"""


def list_source_files(source: dict) -> list[Path]:
    return list_available_docs(get_source_data_path(source))


def save_uploaded_files(source: dict, uploaded_files) -> list[Path]:
    """Save Streamlit UploadedFile objects into the dataset folder."""
    payloads = [(uploaded.name, uploaded.getvalue()) for uploaded in uploaded_files]
    saved, _skipped = save_dataset_files(source, payloads)
    return saved


def save_dataset_files(
    source: dict,
    files: list[tuple[str, bytes]],
) -> tuple[list[Path], list[dict]]:
    """Write uploaded bytes into the dataset folder. Returns saved paths and skipped entries."""
    dest = get_source_data_path(source)
    saved: list[Path] = []
    skipped: list[dict] = []
    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    for name, data in files:
        if not name:
            skipped.append({"name": name or "(unnamed)", "reason": "Missing file name"})
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            skipped.append({"name": name, "reason": f"Unsupported type — use {supported}"})
            continue
        target = dest / Path(name).name
        target.write_bytes(data)
        saved.append(target)
    return saved, skipped


def ingest_source_files(
    source: dict,
    file_paths: list[Path],
    embedder,
    *,
    replace_existing: bool = True,
) -> dict:
    profile = get_rag_profile(source["id"])
    report = ingest_files(
        file_paths,
        embedder,
        replace_existing=replace_existing,
        domain_id=source["domain_id"],
        source_id=source["id"],
        rag_profile_id=profile["id"] if profile else None,
        domain_slug=source["domain_slug"],
        source_slug=source["slug"],
        chunk_size=profile["chunk_size"] if profile else CHUNK_SIZE,
        chunk_overlap=profile["chunk_overlap"] if profile else CHUNK_OVERLAP,
    )
    if profile:
        profile_items = _profile_supplement_items(source, profile)
        if profile_items:
            upsert_chunks(profile_items, embedder)
            report["profile_chunks"] = len(profile_items)
    update_rag_profile(source["id"], touch_ingested=True)
    return report


def _profile_supplement_items(source: dict, profile: dict) -> list[dict]:
    """Embed RAG profile instructions — not raw dataset rows."""
    prefix = f"{source['domain_slug']}_{source['slug']}"
    chunk_size = profile["chunk_size"]
    chunk_overlap = profile["chunk_overlap"]
    body = (profile.get("instructions") or "").strip()
    if not body:
        return []
    items: list[dict] = []
    for i, chunk in enumerate(chunk_text(body, chunk_size, chunk_overlap)):
        items.append(
            {
                "id": f"{prefix}_instructions_{i}",
                "source_file": f"{source['slug']}_instructions",
                "chunk_id": f"instr_{i:02d}",
                "content": chunk,
                "domain_id": source["domain_id"],
                "source_id": source["id"],
                "rag_profile_id": profile["id"],
            }
        )
    return items


def ingest_source_rag(
    source: dict,
    embedder,
    *,
    table_ids: list[str] | None = None,
    file_names: list[str] | None = None,
) -> dict:
    """Ingest RAG-enabled tables (structured) or files (unstructured) for a dataset."""
    if source.get("source_type") == "structured":
        from catalog_rag_service import index_structured_catalog

        if table_ids is not None and len(table_ids) == 0:
            return {
                "skipped": True,
                "catalog_chunks": 0,
                "removed_chunks": 0,
                "metadata_tables": 0,
                "lookup_tables": 0,
            }
        return index_structured_catalog(
            source,
            embedder,
            replace_existing=not table_ids,
            table_ids=table_ids,
        )

    profile = get_rag_profile(source["id"]) or {}
    default_chunk_size = profile.get("chunk_size") or CHUNK_SIZE
    default_chunk_overlap = profile.get("chunk_overlap") or CHUNK_OVERLAP
    rag_by_file = {row["file_name"]: row for row in list_source_file_rag(source["id"])}

    all_paths = list_source_files(source)
    if file_names:
        allowed = set(file_names)
        all_paths = [p for p in all_paths if p.name in allowed]

    report: dict = {
        "files": [],
        "total_chunks": 0,
        "deleted_chunks": 0,
        "errors": [],
        "catalog_chunks": 0,
    }

    for file_path in all_paths:
        settings = rag_by_file.get(file_path.name, {})
        rag_enabled = settings.get("rag_enabled", True)
        if not rag_enabled:
            deleted = delete_chunks_by_source(
                file_path.name,
                source_id=source["id"],
                domain_id=source["domain_id"],
            )
            report["deleted_chunks"] += deleted
            continue

        chunk_size = settings.get("chunk_size") or default_chunk_size
        chunk_overlap = settings.get("chunk_overlap") or default_chunk_overlap
        try:
            deleted = delete_chunks_by_source(
                file_path.name,
                source_id=source["id"],
                domain_id=source["domain_id"],
            )
            items = build_items_for_file(
                file_path,
                domain_slug=source["domain_slug"],
                source_slug=source["slug"],
                domain_id=source["domain_id"],
                source_id=source["id"],
                rag_profile_id=profile.get("id"),
                chunk_size=int(chunk_size),
                chunk_overlap=int(chunk_overlap),
            )
            count = upsert_chunks(items, embedder)
            upsert_source_file_rag(source["id"], file_path.name, touch_ingested=True)
            report["files"].append(
                {
                    "source_file": file_path.name,
                    "chunks_ingested": count,
                    "chunks_deleted": deleted,
                    "status": "success",
                }
            )
            report["total_chunks"] += count
            report["deleted_chunks"] += deleted
        except Exception as exc:
            report["errors"].append(
                {"source_file": file_path.name, "error": str(exc), "status": "failed"}
            )

    profile_items = _profile_supplement_items(source, profile) if profile else []
    if profile_items:
        upsert_chunks(profile_items, embedder)
        report["profile_chunks"] = len(profile_items)

    if profile:
        update_rag_profile(source["id"], touch_ingested=True)
    report["catalog_chunks"] = report["total_chunks"]
    return report


def save_dataset_rag_settings(
    source_id: str,
    *,
    profile: dict | None = None,
    tables: list[dict] | None = None,
    files: list[dict] | None = None,
) -> dict:
    source = get_source(source_id=source_id)
    if profile:
        update_rag_profile(source_id, **profile)
    updated_tables = bulk_update_table_rag(source_id, tables or []) if tables is not None else None
    updated_files = (
        bulk_update_source_file_rag(source_id, files or []) if files is not None else None
    )
    chunks_removed = 0
    if source and tables is not None:
        from catalog_db import get_table_metadata
        from catalog_rag_service import delete_table_rag_chunks

        for item in tables:
            if item.get("rag_enabled") is False:
                table = get_table_metadata(item.get("id", ""))
                if table:
                    chunks_removed += delete_table_rag_chunks(source, table)
    if source and files is not None:
        for item in files:
            if item.get("rag_enabled") is False:
                file_name = (item.get("file_name") or "").strip()
                if file_name:
                    chunks_removed += delete_chunks_by_source(
                        file_name,
                        source_id=source_id,
                        domain_id=source.get("domain_id"),
                    )
    return {
        "profile": get_rag_profile(source_id),
        "tables": updated_tables,
        "files": updated_files,
        "chunks_removed": chunks_removed,
    }


def list_dataset_assets(source: dict) -> list[dict]:
    from dataset_connectors.registry import asset_to_dict, get_connector_for_source

    connector = get_connector_for_source(source)
    return [asset_to_dict(asset) for asset in connector.list_assets(source)]


def test_dataset_connection(source: dict) -> tuple[bool, str]:
    from dataset_connectors.registry import get_connector_for_source

    return get_connector_for_source(source).test_connection(source)


def sync_dataset_source(
    source: dict,
    *,
    asset_ids: list[str] | None = None,
    full: bool = False,
) -> dict:
    from dataset_connectors.registry import get_connector_for_source, sync_result_to_dict

    connector = get_connector_for_source(source)
    result = connector.sync(source, asset_ids=asset_ids, full=full)
    cfg = dict(source.get("config") or {})
    cfg["last_sync_at"] = datetime.now(UTC).isoformat()
    cfg["last_sync_errors"] = len(result.errors)
    update_source(source["id"], config=cfg)
    payload = sync_result_to_dict(result)
    payload["connector"] = source.get("connector")
    return payload


def build_dataset_schema_context(source: dict) -> dict:
    from dataset_connectors.registry import get_connector_for_source

    return get_connector_for_source(source).build_schema_context(source)


def get_source_ingest_map(source_id: str) -> dict[str, dict]:
    rows = list_ingested_sources(source_id=source_id)
    return {row["source_file"]: row for row in rows}


def delete_dataset(source_id: str) -> dict:
    """Delete a dataset and its catalog rows; remove ingested chunks when tagged."""
    source = get_source(source_id=source_id)
    if not source:
        return {"deleted": False}
    chunks_removed = delete_chunks_for_source(source_id)
    deleted = delete_source(source_id)
    return {"deleted": deleted, "chunks_removed": chunks_removed, "name": source["name"]}


def resolve_domain(identifier: str) -> dict | None:
    """Resolve domain by UUID, slug, or display name."""
    import uuid

    try:
        uuid.UUID(identifier)
        domain = get_domain(domain_id=identifier)
        if domain:
            return domain
    except ValueError:
        pass
    domain = get_domain(slug=identifier.lower())
    if domain:
        return domain
    for row in list_domains(enabled_only=False):
        if row["name"].lower() == identifier.lower():
            return get_domain(domain_id=row["id"])
    return None


def resolve_domains(identifiers: list[str]) -> list[dict]:
    """Resolve many domain identifiers; unknown entries are skipped."""
    seen: set[str] = set()
    resolved: list[dict] = []
    for identifier in identifiers:
        key = identifier.strip()
        if not key:
            continue
        domain = resolve_domain(key)
        if not domain or domain["id"] in seen:
            continue
        seen.add(domain["id"])
        resolved.append(domain)
    return resolved


def normalize_domain_overrides(
    domain_override: str | None = None,
    domain_overrides: list[str] | None = None,
) -> list[str]:
    """Merge legacy single override with multi-select slugs."""
    if domain_overrides:
        return [item.strip() for item in domain_overrides if item and item.strip()]
    if domain_override and domain_override.strip():
        return [domain_override.strip()]
    return []


def get_routing_context() -> list[dict]:
    """Domains with sources for question routing."""
    from routing_cache import get_cached_routing_context

    return get_cached_routing_context()
