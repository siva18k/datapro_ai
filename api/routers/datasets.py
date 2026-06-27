from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.deps import get_embedder
from api.llm import generate_answer
from catalog_db import (
    create_source,
    delete_table_metadata,
    get_column_metadata,
    get_rag_profile,
    get_source,
    get_table_metadata,
    list_column_metadata,
    list_source_file_rag,
    list_sources,
    list_table_metadata,
    sync_columns_from_introspection,
    update_source,
    update_table_metadata,
    upsert_column_metadata,
    upsert_table_metadata,
)
from catalog_service import (
    build_dataset_schema_context,
    delete_dataset,
    get_dataset_definition_path,
    get_source_data_path,
    get_source_ingest_map,
    ingest_source_files,
    ingest_source_rag,
    list_dataset_assets,
    list_source_files,
    load_dataset_definition,
    save_dataset_definition,
    save_dataset_files,
    save_dataset_rag_settings,
    sync_dataset_source,
    test_dataset_connection,
)
from dataset_connectors.registry import CONNECTOR_SOURCE_TYPES, is_content_connector, is_remote_connector
from ingest_service import SUPPORTED_EXTENSIONS
from structured_db import (
    list_schema_tables,
    list_table_columns,
    postgres_config_from_source,
)
from catalog_definition import draft_dataset_definition, strip_markdown_fences
from relationship_inference import build_relationships_section, merge_relationships_into_definition

router = APIRouter(tags=["datasets"])

DATASET_TYPES = CONNECTOR_SOURCE_TYPES


class SyncBody(BaseModel):
    asset_ids: list[str] | None = None
    full: bool = False


class DatasetCreate(BaseModel):
    name: str
    description: str = ""
    connector: str
    config: dict | None = None


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    connector: str | None = None


class DefinitionBody(BaseModel):
    markdown: str


class TablesBody(BaseModel):
    table_names: list[str]


class TableUpdate(BaseModel):
    definition: str | None = None
    enabled: bool | None = None
    table_role: str | None = None
    rag_enabled: bool | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class TableRagRow(BaseModel):
    id: str
    rag_enabled: bool | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class FileRagRow(BaseModel):
    file_name: str
    rag_enabled: bool | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class RagProfileUpdate(BaseModel):
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    instructions: str | None = None


class RagSettingsBody(BaseModel):
    profile: RagProfileUpdate | None = None
    tables: list[TableRagRow] = Field(default_factory=list)
    files: list[FileRagRow] = Field(default_factory=list)


class RagIngestBody(BaseModel):
    table_ids: list[str] | None = None
    file_names: list[str] | None = None


class ColumnUpdate(BaseModel):
    labels: list[str] | None = None
    description: str | None = None


class IngestBody(BaseModel):
    file_names: list[str]


@router.get("/domains/{domain_id}/datasets")
def list_domain_datasets(domain_id: str, enabled_only: bool = False):
    return list_sources(domain_id=domain_id, enabled_only=enabled_only)


@router.post("/domains/{domain_id}/datasets", status_code=201)
def create_dataset(domain_id: str, body: DatasetCreate):
    if body.connector not in DATASET_TYPES:
        raise HTTPException(400, f"Unknown connector: {body.connector}")
    return create_source(
        domain_id,
        body.name,
        description=body.description,
        source_type=DATASET_TYPES[body.connector],
        connector=body.connector,
        config=body.config,
    )


@router.get("/datasets/supported-file-types")
def supported_file_types():
    return {
        "extensions": sorted(SUPPORTED_EXTENSIONS),
        "accept": ",".join(ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)),
    }


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    row = get_source(source_id=dataset_id)
    if not row:
        raise HTTPException(404, "Dataset not found")
    return row


@router.patch("/datasets/{dataset_id}")
def patch_dataset(dataset_id: str, body: DatasetUpdate):
    if not get_source(source_id=dataset_id):
        raise HTTPException(404, "Dataset not found")
    fields = body.model_dump(exclude_none=True)
    if "connector" in fields:
        connector = fields.pop("connector")
        if connector not in DATASET_TYPES:
            raise HTTPException(400, f"Unknown connector: {connector}")
        update_source(dataset_id, connector=connector, source_type=DATASET_TYPES[connector])
    if fields:
        update_source(dataset_id, **fields)
    return get_source(source_id=dataset_id)


@router.delete("/datasets/{dataset_id}")
def remove_dataset(dataset_id: str):
    if not get_source(source_id=dataset_id):
        raise HTTPException(404, "Dataset not found")
    result = delete_dataset(dataset_id)
    if not result.get("deleted"):
        raise HTTPException(500, "Failed to delete dataset")
    return result


@router.get("/datasets/{dataset_id}/summary")
def dataset_summary(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    cfg = source.get("config") or {}
    connector = source["connector"]
    out: dict = {"connector": connector, "name": source["name"]}
    if connector == "postgres":
        out["host"] = cfg.get("host")
        out["schema"] = cfg.get("schema")
        out["table_count"] = len(list_table_metadata(dataset_id))
    elif is_content_connector(connector):
        files = list_source_files(source)
        ingested = get_source_ingest_map(dataset_id)
        out["file_count"] = len(files)
        out["chunk_count"] = sum(int(v["chunk_count"]) for v in ingested.values())
        if is_remote_connector(connector):
            out["last_sync_at"] = cfg.get("last_sync_at")
            out["asset_count"] = len(list_dataset_assets(source))
            if connector == "api":
                out["base_url"] = cfg.get("base_url")
            else:
                out["url"] = cfg.get("url")
    else:
        out["url"] = cfg.get("url")
    return out


@router.post("/datasets/{dataset_id}/test-connection")
def test_connection(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    ok, msg = test_dataset_connection(source)
    return {"ok": ok, "message": msg}


@router.get("/datasets/{dataset_id}/assets")
def dataset_assets(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    return {"assets": list_dataset_assets(source), "connector": source.get("connector")}


@router.post("/datasets/{dataset_id}/sync")
def sync_dataset(dataset_id: str, body: SyncBody | None = None):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    payload = body or SyncBody()
    result = sync_dataset_source(
        source,
        asset_ids=payload.asset_ids,
        full=payload.full,
    )
    return result


@router.get("/datasets/{dataset_id}/remote-tables")
def remote_tables(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source or source["connector"] != "postgres":
        raise HTTPException(400, "Dataset is not a postgres connection")
    try:
        tables = list_schema_tables(postgres_config_from_source(source))
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"tables": tables}


@router.get("/datasets/{dataset_id}/tables")
def catalog_tables(dataset_id: str):
    return list_table_metadata(dataset_id)


@router.post("/datasets/{dataset_id}/tables")
def add_tables(dataset_id: str, body: TablesBody):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    if source["connector"] != "postgres":
        raise HTTPException(400, "Only postgres datasets support table cataloging")
    schema = (source.get("config") or {}).get("schema") or "public"
    pg_cfg = postgres_config_from_source(source)
    created = []
    for name in body.table_names:
        table = upsert_table_metadata(dataset_id, schema, name)
        try:
            discovered = list_table_columns(pg_cfg, name)
            sync_columns_from_introspection(table["id"], discovered)
        except Exception as exc:
            raise HTTPException(
                502,
                f"Table {name} cataloged but column sync failed: {exc}",
            ) from exc
        created.append(table)
    return created


@router.patch("/tables/{table_id}")
def patch_table(table_id: str, body: TableUpdate):
    fields = body.model_dump(exclude_none=True)
    if fields:
        update_table_metadata(table_id, **fields)
    return {"ok": True}


@router.delete("/tables/{table_id}")
def remove_table(table_id: str):
    table = get_table_metadata(table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    delete_table_metadata(table_id)
    return {"ok": True, "source_id": table["source_id"], "table_name": table["table_name"]}


@router.post("/tables/{table_id}/sync-columns")
def sync_columns(table_id: str):
    from catalog_db import get_table_metadata

    table = get_table_metadata(table_id)
    if not table:
        raise HTTPException(404, "Table not found")
    source = get_source(source_id=table["source_id"])
    if not source:
        raise HTTPException(404, "Dataset not found")
    pg_cfg = postgres_config_from_source(source)
    try:
        discovered = list_table_columns(pg_cfg, table["table_name"])
        result = sync_columns_from_introspection(table_id, discovered)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
    return result


@router.get("/tables/{table_id}/columns")
def table_columns(table_id: str):
    return list_column_metadata(table_id)


@router.patch("/columns/{column_id}")
def patch_column(column_id: str, body: ColumnUpdate):
    col = get_column_metadata(column_id)
    if not col:
        raise HTTPException(404, "Column not found")
    fields: dict = {}
    if body.labels is not None:
        fields["labels"] = body.labels
    if body.description is not None:
        fields["description"] = body.description
    if fields:
        upsert_column_metadata(col["table_metadata_id"], col["column_name"], **fields)
    updated = get_column_metadata(column_id)
    return updated or {"ok": True}


@router.get("/datasets/{dataset_id}/schema-context")
def schema_context(dataset_id: str):
    """LLM-ready schema: definitions, table defs, column labels (for text-to-SQL)."""
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    try:
        return build_dataset_schema_context(source)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/datasets/{dataset_id}/definition/relationships")
def get_definition_relationships(dataset_id: str):
    """Infer referential relationships from cataloged tables and return markdown for the definition."""
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    if source.get("connector") != "postgres":
        raise HTTPException(400, "Relationship inference is only available for postgres datasets")
    try:
        payload = build_relationships_section(dataset_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    definition_md = strip_markdown_fences(load_dataset_definition(source))
    merged = merge_relationships_into_definition(definition_md, payload["markdown_section"])
    return {
        **payload,
        "merged_markdown": merged,
    }


@router.get("/datasets/{dataset_id}/definition")
def get_definition(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    return {
        "markdown": load_dataset_definition(source),
        "path": str(get_dataset_definition_path(source)),
    }


@router.put("/datasets/{dataset_id}/definition")
def put_definition(dataset_id: str, body: DefinitionBody):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    markdown = strip_markdown_fences(body.markdown)
    save_dataset_definition(source, markdown)
    return {"ok": True, "path": str(get_dataset_definition_path(source))}


@router.post("/datasets/{dataset_id}/definition/draft")
def draft_definition(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    try:
        md = draft_dataset_definition(dataset_id, generate_fn=generate_answer)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    save_dataset_definition(source, md)
    return {"markdown": md}


@router.get("/datasets/{dataset_id}/files")
def list_files(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    files = list_source_files(source)
    ingested = get_source_ingest_map(dataset_id)
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "ingested": f.name in ingested,
            "chunks": int(ingested[f.name]["chunk_count"]) if f.name in ingested else 0,
        }
        for f in files
    ]


@router.post("/datasets/{dataset_id}/upload")
async def upload_dataset_files(
    dataset_id: str,
    files: list[UploadFile] = File(...),
):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    if source.get("connector") not in ("upload", "file_path"):
        raise HTTPException(400, "Upload is only supported for file-based datasets")
    if not files:
        raise HTTPException(400, "No files provided")

    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        name = upload.filename or ""
        payloads.append((name, await upload.read()))

    saved_paths, skipped = save_dataset_files(source, payloads)
    if not saved_paths and skipped:
        detail = "; ".join(f"{s['name']}: {s['reason']}" for s in skipped)
        raise HTTPException(400, detail or "No supported files uploaded")

    return {
        "saved": [p.name for p in saved_paths],
        "skipped": skipped,
    }


@router.post("/datasets/{dataset_id}/ingest")
def ingest(dataset_id: str, body: IngestBody):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    if source.get("source_type") == "structured":
        raise HTTPException(
            400,
            "Structured datasets use the RAG tab in Catalog for table indexing.",
        )
    base = get_source_data_path(source)
    paths = [base / name for name in body.file_names]
    missing = [n for n, p in zip(body.file_names, paths) if not p.exists()]
    if missing:
        raise HTTPException(400, f"Files not found: {', '.join(missing)}")
    report = ingest_source_files(source, paths, get_embedder())
    return report


@router.get("/datasets/{dataset_id}/rag")
def dataset_rag_settings(dataset_id: str):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    profile = get_rag_profile(dataset_id)
    if not profile:
        raise HTTPException(404, "RAG profile not found")
    ingested = get_source_ingest_map(dataset_id)
    out: dict = {"source": source, "profile": profile}
    if source.get("source_type") == "structured":
        tables = list_table_metadata(dataset_id)
        for table in tables:
            prefix = f"catalog_meta/{source.get('domain_slug')}/{source.get('slug')}/{table['table_name']}"
            lookup = f"lookup_data/{source.get('domain_slug')}/{source.get('slug')}/{table['table_name']}"
            table["ingested"] = prefix in ingested or lookup in ingested
            table["chunk_count"] = int(ingested.get(prefix, {}).get("chunk_count", 0)) + int(
                ingested.get(lookup, {}).get("chunk_count", 0)
            )
        out["tables"] = tables
    else:
        file_rows = {r["file_name"]: r for r in list_source_file_rag(dataset_id)}
        files = []
        for path in list_source_files(source):
            settings = file_rows.get(path.name, {})
            row = {
                "file_name": path.name,
                "rag_enabled": settings.get("rag_enabled", True),
                "chunk_size": settings.get("chunk_size"),
                "chunk_overlap": settings.get("chunk_overlap"),
                "ingested": path.name in ingested,
                "chunk_count": int(ingested.get(path.name, {}).get("chunk_count", 0)),
            }
            files.append(row)
        out["files"] = files
    return out


@router.put("/datasets/{dataset_id}/rag/settings")
def save_rag_settings(dataset_id: str, body: RagSettingsBody):
    if not get_source(source_id=dataset_id):
        raise HTTPException(404, "Dataset not found")
    profile_fields = body.profile.model_dump(exclude_none=True) if body.profile else None
    table_payload = [t.model_dump() for t in body.tables] if body.tables else None
    file_payload = [f.model_dump() for f in body.files] if body.files else None
    result = save_dataset_rag_settings(
        dataset_id,
        profile=profile_fields,
        tables=table_payload,
        files=file_payload,
    )
    return result


@router.post("/datasets/{dataset_id}/rag/ingest")
def rag_ingest(dataset_id: str, body: RagIngestBody | None = None):
    source = get_source(source_id=dataset_id)
    if not source:
        raise HTTPException(404, "Dataset not found")
    payload = body or RagIngestBody()
    if source.get("source_type") == "structured":
        if payload.table_ids is not None and len(payload.table_ids) == 0:
            return {
                "skipped": True,
                "catalog_chunks": 0,
                "removed_chunks": 0,
                "message": "No changed tables to ingest.",
            }
        table_ids = payload.table_ids
        file_names = None
    else:
        if payload.file_names is not None and len(payload.file_names) == 0:
            return {
                "skipped": True,
                "catalog_chunks": 0,
                "total_chunks": 0,
                "message": "No changed files to ingest.",
            }
        table_ids = None
        file_names = payload.file_names
    refreshed = get_source(source_id=dataset_id)
    if refreshed and is_remote_connector(refreshed.get("connector", "")) and not list_source_files(refreshed):
        sync_dataset_source(refreshed)
        refreshed = get_source(source_id=dataset_id)
    try:
        return ingest_source_rag(
            refreshed or source,
            get_embedder(),
            table_ids=table_ids,
            file_names=file_names,
        )
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
