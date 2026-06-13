"""High-level catalog operations: paths, ingest, domain context."""

from __future__ import annotations

from pathlib import Path

from catalog_db import (
    create_domain,
    create_source,
    delete_source,
    get_domain,
    get_rag_profile,
    get_source,
    init_catalog,
    list_domains,
    list_sources,
    update_rag_profile,
    update_source,
)
from db import delete_chunks_for_source, list_ingested_sources, upsert_chunks
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


def get_source_data_path(source: dict) -> Path:
    cfg = source.get("config") or {}
    path = cfg.get("path", "sample_docs")
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
    """Embed RAG profile instructions and glossary — not raw dataset rows."""
    prefix = f"{source['domain_slug']}_{source['slug']}"
    chunk_size = profile["chunk_size"]
    chunk_overlap = profile["chunk_overlap"]
    items: list[dict] = []
    for name, text, chunk_prefix in (
        ("instructions", profile.get("instructions") or "", "instr"),
        ("metadata", profile.get("metadata_text") or "", "meta"),
    ):
        body = text.strip()
        if not body:
            continue
        for i, chunk in enumerate(chunk_text(body, chunk_size, chunk_overlap)):
            items.append(
                {
                    "id": f"{prefix}_{name}_{i}",
                    "source_file": f"{source['slug']}_{name}",
                    "chunk_id": f"{chunk_prefix}_{i:02d}",
                    "content": chunk,
                    "domain_id": source["domain_id"],
                    "source_id": source["id"],
                    "rag_profile_id": profile["id"],
                }
            )
    return items


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
