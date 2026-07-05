import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    project_env = Path(__file__).resolve().parent / ".env"
    # Project .env is authoritative — override stale/empty vars inherited from the shell or Vite.
    load_dotenv(project_env, override=True)


def _load_config():
    cfg: dict = {}
    for key, value in os.environ.items():
        if key.startswith(("PG", "DATABASE")) or key == "DB_SCHEMA":
            cfg[key] = value
    return cfg


def get_db_config():
    """Resolve DB connection from project .env (Settings), not only process environment."""
    from settings_service import get_raw_settings

    cfg = get_raw_settings()
    host = (cfg.get("PGHOST") or "").strip()
    port = int(cfg.get("PGPORT") or 5432)
    user = (cfg.get("PGUSER") or "").strip()
    password = (cfg.get("PGPASSWORD") or "").strip()
    database = (cfg.get("PGDATABASE") or "").strip()
    schema = (cfg.get("DB_SCHEMA") or "ragpro").strip() or "ragpro"
    sslmode = (cfg.get("PGSSLMODE") or "require").strip() or "require"

    if cfg.get("DATABASE_URL"):
        parsed = urlparse(cfg["DATABASE_URL"])
        host = host or (parsed.hostname or "")
        port = int(cfg.get("PGPORT") or parsed.port or 5432)
        user = user or unquote(parsed.username or "")
        password = password or unquote(parsed.password or "")
        database = database or (parsed.path or "").lstrip("/")

    if not all([host, user, password, database]):
        raise RuntimeError(
            "Missing DB config. Set DATABASE_URL or PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE "
            f"in {Path(__file__).resolve().parent / '.env'}."
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "schema": schema,
        "sslmode": sslmode,
    }


def _safe_identifier(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return name


def _ssl_context(sslmode):
    if sslmode in ("require", "verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if sslmode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def connect():
    import pg8000.native

    cfg = get_db_config()
    conn = pg8000.native.Connection(
        user=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
        ssl_context=_ssl_context(cfg["sslmode"]),
        timeout=15,
    )
    return conn, _safe_identifier(cfg["schema"])


def vector_literal(values):
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


_CATALOG_COLUMNS: bool | None = None
_SOURCE_CHUNK_UNIQUE: bool | None = None
_TABLE_METADATA_COLUMN: bool | None = None


def knowledge_chunks_has_table_metadata_column() -> bool:
    global _TABLE_METADATA_COLUMN
    if _TABLE_METADATA_COLUMN is not None:
        return _TABLE_METADATA_COLUMN
    try:
        conn, schema = connect()
        try:
            rows = conn.run(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'knowledge_chunks'
                  AND column_name = 'table_metadata_id'
                LIMIT 1
                """,
                schema=schema,
            )
            _TABLE_METADATA_COLUMN = bool(rows)
        finally:
            conn.close()
    except Exception:
        _TABLE_METADATA_COLUMN = False
    return _TABLE_METADATA_COLUMN


def knowledge_chunks_has_embedding_model_column() -> bool:
    global _CATALOG_COLUMNS
    # Reuse the existing cached flag where appropriate — check explicitly to avoid
    # repeated queries when calling upsert_chunks frequently.
    try:
        conn, schema = connect()
        try:
            rows = conn.run(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'knowledge_chunks'
                  AND column_name = 'embedding_model'
                LIMIT 1
                """,
                schema=schema,
            )
            return bool(rows)
        finally:
            conn.close()
    except Exception:
        return False


def knowledge_chunks_has_catalog_columns() -> bool:
    global _CATALOG_COLUMNS
    if _CATALOG_COLUMNS is not None:
        return _CATALOG_COLUMNS
    try:
        conn, schema = connect()
        try:
            rows = conn.run(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'knowledge_chunks'
                  AND column_name IN ('domain_id', 'source_id', 'rag_profile_id')
                """,
                schema=schema,
            )
            _CATALOG_COLUMNS = len(rows) >= 3
        finally:
            conn.close()
    except Exception:
        _CATALOG_COLUMNS = False
    return _CATALOG_COLUMNS


def knowledge_chunks_has_source_chunk_unique() -> bool:
    """True when (source_file, chunk_id) has a unique constraint (catalog re-index safety)."""
    global _SOURCE_CHUNK_UNIQUE
    if _SOURCE_CHUNK_UNIQUE is not None:
        return _SOURCE_CHUNK_UNIQUE
    try:
        conn, schema = connect()
        try:
            rows = conn.run(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE c.conname = 'ux_knowledge_chunks_source_chunk'
                  AND n.nspname = :schema
                LIMIT 1
                """,
                schema=schema,
            )
            _SOURCE_CHUNK_UNIQUE = bool(rows)
        finally:
            conn.close()
    except Exception:
        _SOURCE_CHUNK_UNIQUE = False
    return _SOURCE_CHUNK_UNIQUE


def chunk_verify_sql(source_file: str, chunk_id: str) -> str:
    """Read-only SQL to inspect a retrieved chunk in knowledge_chunks."""
    schema = _safe_identifier(get_db_config()["schema"])
    sf = source_file.replace("'", "''")
    cid = chunk_id.replace("'", "''")
    return (
        f"SELECT id, source_file, chunk_id, domain_id, source_id,\n"
        f"       LEFT(content, 300) AS content_preview, updated_at\n"
        f"FROM {schema}.knowledge_chunks\n"
        f"WHERE source_file = '{sf}' AND chunk_id = '{cid}';"
    )


def search_chunks(
    question,
    embedder,
    top_k=3,
    query_vector=None,
    *,
    domain_id: str | None = None,
    domain_ids: list[str] | None = None,
    source_id: str | None = None,
    source_ids: list[str] | None = None,
    source_files: list[str] | None = None,
    fuzzy: bool = True,
):
    from query_fuzzy import encode_search_queries, get_search_query_variants, merge_ranked_chunks

    if fuzzy and question:
        variants = get_search_query_variants(question)
        if len(variants) > 1:
            per_variant_k = max(top_k * 2, min(top_k + 4, 12))
            vectors = encode_search_queries(embedder, question)
            result_lists = [
                _search_chunks_with_vector(
                    vector,
                    top_k=per_variant_k,
                    domain_id=domain_id,
                    domain_ids=domain_ids,
                    source_id=source_id,
                    source_ids=source_ids,
                    source_files=source_files,
                )
                for vector in vectors
            ]
            return merge_ranked_chunks(result_lists, top_k)

    if query_vector is None:
        query_vector = embedder.encode([question])[0]
    return _search_chunks_with_vector(
        query_vector,
        top_k=top_k,
        domain_id=domain_id,
        domain_ids=domain_ids,
        source_id=source_id,
        source_ids=source_ids,
        source_files=source_files,
    )


def _search_chunks_with_vector(
    query_vector,
    *,
    top_k=3,
    domain_id: str | None = None,
    domain_ids: list[str] | None = None,
    source_id: str | None = None,
    source_ids: list[str] | None = None,
    source_files: list[str] | None = None,
):
    embedding = vector_literal(query_vector)
    conn, schema = connect()
    try:
        has_catalog = knowledge_chunks_has_catalog_columns()
        clauses = ["embedding IS NOT NULL", "vector_dims(embedding) = vector_dims(:embedding::vector)"]
        params: dict = {"embedding": embedding}
        if has_catalog:
            if domain_id:
                clauses.append("domain_id = :domain_id::uuid")
                params["domain_id"] = domain_id
            elif domain_ids:
                placeholders = ", ".join(f":did_{i}::uuid" for i in range(len(domain_ids)))
                clauses.append(f"domain_id IN ({placeholders})")
                for i, did in enumerate(domain_ids):
                    params[f"did_{i}"] = did
            if source_id:
                clauses.append("source_id = :source_id::uuid")
                params["source_id"] = source_id
            if source_ids:
                placeholders = ", ".join(f":sid_{i}::uuid" for i in range(len(source_ids)))
                clauses.append(f"source_id IN ({placeholders})")
                for i, sid in enumerate(source_ids):
                    params[f"sid_{i}"] = sid
            if source_files:
                placeholders = ", ".join(f":sf_{i}" for i in range(len(source_files)))
                clauses.append(f"source_file IN ({placeholders})")
                for i, sf in enumerate(source_files):
                    params[f"sf_{i}"] = sf
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        catalog_cols = ", domain_id::text, source_id::text" if has_catalog else ", NULL::text, NULL::text"

        # Prefer SQL top-k (fast). pg8000 may return no rows with ORDER BY+LIMIT on
        # some setups — fall back to full scan + Python sort.
        candidate_limit = max(top_k * 40, 200)
        params["candidate_limit"] = candidate_limit
        rows = conn.run(
            f"""
            SELECT source_file, chunk_id, content, distance{catalog_cols}
            FROM (
                SELECT
                    source_file,
                    chunk_id,
                    content,
                    embedding <=> :embedding::vector AS distance
                    {catalog_cols}
                FROM {schema}.knowledge_chunks
                {where}
            ) AS ranked
            ORDER BY distance
            LIMIT :candidate_limit
            """,
            **params,
        )
        if not rows:
            rows = conn.run(
                f"""
                SELECT
                    source_file,
                    chunk_id,
                    content,
                    embedding <=> :embedding::vector AS distance
                    {catalog_cols}
                FROM {schema}.knowledge_chunks
                {where}
                """,
                **params,
            )
            rows.sort(key=lambda row: row[3])
            rows = rows[:top_k]
        else:
            rows = rows[:top_k]
    finally:
        conn.close()

    return [
        {
            "text": row[2],
            "source": row[0],
            "chunk_id": row[1],
            "distance": float(row[3]),
            "domain_id": row[4],
            "source_id": row[5],
        }
        for row in rows
    ]


def upsert_chunks(items, embedder):
    if not items:
        return 0

    conn, schema = connect()
    try:
        has_catalog = knowledge_chunks_has_catalog_columns()
        has_table_meta = knowledge_chunks_has_table_metadata_column()
        conflict_on_source_chunk = knowledge_chunks_has_source_chunk_unique()
        has_embedding_col = knowledge_chunks_has_embedding_model_column() if has_catalog else False
        for item in items:
            embedding = vector_literal(embedder.encode([item["content"]])[0])
            if has_catalog:
                conflict = (
                    "(source_file, chunk_id)"
                    if conflict_on_source_chunk
                    else "(id)"
                )
                table_meta_col = ", table_metadata_id" if has_table_meta else ""
                table_meta_val = ", :table_metadata_id::uuid" if has_table_meta else ""
                table_meta_set = (
                    ", table_metadata_id = EXCLUDED.table_metadata_id"
                    if has_table_meta
                    else ""
                )
                embedding_col = ", embedding_model" if has_embedding_col else ""
                embedding_val = ", :embedding_model" if has_embedding_col else ""
                embedding_set = ", embedding_model = EXCLUDED.embedding_model" if has_embedding_col else ""
                params = {
                    "id": item["id"],
                    "source_file": item["source_file"],
                    "chunk_id": item["chunk_id"],
                    "content": item["content"],
                    "embedding": embedding,
                    "domain_id": item.get("domain_id"),
                    "source_id": item.get("source_id"),
                    "rag_profile_id": item.get("rag_profile_id"),
                    "embedding_model": item.get("embedding_model") or None,
                }
                if has_table_meta:
                    params["table_metadata_id"] = item.get("table_metadata_id")
                conn.run(
                    f"""
                    INSERT INTO {schema}.knowledge_chunks
                        (id, source_file, chunk_id, content, embedding,
                         domain_id, source_id, rag_profile_id{table_meta_col}{embedding_col})
                    VALUES
                        (:id, :source_file, :chunk_id, :content, :embedding::vector,
                         :domain_id::uuid, :source_id::uuid, :rag_profile_id::uuid{table_meta_val}{embedding_val})
                    ON CONFLICT {conflict} DO UPDATE SET
                        id = EXCLUDED.id,
                        source_file = EXCLUDED.source_file,
                        chunk_id = EXCLUDED.chunk_id,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        domain_id = EXCLUDED.domain_id,
                        source_id = EXCLUDED.source_id,
                        rag_profile_id = EXCLUDED.rag_profile_id{table_meta_set}{embedding_set},
                        updated_at = now()
                    """,
                    **params,
                )
            else:
                conflict = (
                    "(source_file, chunk_id)"
                    if conflict_on_source_chunk
                    else "(id)"
                )
                if has_embedding_col:
                    conn.run(
                        f"""
                        INSERT INTO {schema}.knowledge_chunks
                            (id, source_file, chunk_id, content, embedding, embedding_model)
                        VALUES
                            (:id, :source_file, :chunk_id, :content, :embedding::vector, :embedding_model)
                        ON CONFLICT {conflict} DO UPDATE SET
                            id = EXCLUDED.id,
                            source_file = EXCLUDED.source_file,
                            chunk_id = EXCLUDED.chunk_id,
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            embedding_model = EXCLUDED.embedding_model,
                            updated_at = now()
                        """,
                        id=item["id"],
                        source_file=item["source_file"],
                        chunk_id=item["chunk_id"],
                        content=item["content"],
                        embedding=embedding,
                        embedding_model=item.get("embedding_model") or None,
                    )
                else:
                    conn.run(
                        f"""
                        INSERT INTO {schema}.knowledge_chunks
                            (id, source_file, chunk_id, content, embedding)
                        VALUES
                            (:id, :source_file, :chunk_id, :content, :embedding::vector)
                        ON CONFLICT {conflict} DO UPDATE SET
                            id = EXCLUDED.id,
                            source_file = EXCLUDED.source_file,
                            chunk_id = EXCLUDED.chunk_id,
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            updated_at = now()
                        """,
                        id=item["id"],
                        source_file=item["source_file"],
                        chunk_id=item["chunk_id"],
                        content=item["content"],
                        embedding=embedding,
                    )
    finally:
        conn.close()

    return len(items)


def list_ingested_sources(*, domain_id: str | None = None, source_id: str | None = None):
    conn, schema = connect()
    try:
        has_catalog = knowledge_chunks_has_catalog_columns()
        clauses = []
        params: dict = {}
        if has_catalog:
            if domain_id:
                clauses.append("domain_id = :domain_id::uuid")
                params["domain_id"] = domain_id
            if source_id:
                clauses.append("source_id = :source_id::uuid")
                params["source_id"] = source_id
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        group_cols = "source_file, domain_id, source_id" if has_catalog else "source_file"
        catalog_sel = ", domain_id::text, source_id::text" if has_catalog else ", NULL::text, NULL::text"
        # Include the embedding_model(s) used for each source_file (comma-separated distinct list)
        embedding_agg = ", string_agg(DISTINCT embedding_model, ',') FILTER (WHERE embedding_model IS NOT NULL)"
        rows = conn.run(
            f"""
            SELECT
                source_file,
                COUNT(*) AS chunk_count,
                MIN(LENGTH(content)) AS min_chars,
                MAX(LENGTH(content)) AS max_chars,
                MAX(updated_at) AS last_ingested
                {embedding_agg}
                {catalog_sel}
            FROM {schema}.knowledge_chunks
            {where}
            GROUP BY {group_cols}
            ORDER BY source_file
            """,
            **params,
        )
    finally:
        conn.close()

    return [
        {
            "source_file": row[0],
            "chunk_count": row[1],
            "min_chars": row[2],
            "max_chars": row[3],
            "last_ingested": row[4],
            "embedding_model": row[5] if has_catalog else None,
            "domain_id": row[6] if has_catalog else None,
            "source_id": row[7] if has_catalog else None,
        }
        for row in rows
    ]


def get_total_chunk_count():
    conn, schema = connect()
    try:
        rows = conn.run(f"SELECT COUNT(*) FROM {schema}.knowledge_chunks")
    finally:
        conn.close()
    return rows[0][0] if rows else 0


def delete_chunks_by_source(
    source_file: str,
    *,
    source_id: str | None = None,
    domain_id: str | None = None,
) -> int:
    conn, schema = connect()
    try:
        has_catalog = knowledge_chunks_has_catalog_columns()
        clauses = ["source_file = :source_file"]
        params: dict = {"source_file": source_file}
        if has_catalog:
            if source_id:
                clauses.append("source_id = :source_id::uuid")
                params["source_id"] = source_id
            if domain_id:
                clauses.append("domain_id = :domain_id::uuid")
                params["domain_id"] = domain_id
        where = " AND ".join(clauses)
        rows = conn.run(
            f"""
            DELETE FROM {schema}.knowledge_chunks
            WHERE {where}
            RETURNING id
            """,
            **params,
        )
    finally:
        conn.close()
    return len(rows)


def delete_chunks_for_source(source_id: str) -> int:
    """Remove all ingested chunks tagged with this dataset source_id."""
    conn, schema = connect()
    try:
        if not knowledge_chunks_has_catalog_columns():
            return 0
        rows = conn.run(
            f"""
            DELETE FROM {schema}.knowledge_chunks
            WHERE source_id = :source_id::uuid
            RETURNING id
            """,
            source_id=source_id,
        )
    finally:
        conn.close()
    return len(rows)


def get_chunk_preview(source_file: str, limit: int = 5):
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT chunk_id, LENGTH(content), content, updated_at
            FROM {schema}.knowledge_chunks
            WHERE source_file = :source_file
            ORDER BY chunk_id
            LIMIT :limit
            """,
            source_file=source_file,
            limit=limit,
        )
    finally:
        conn.close()

    return [
        {
            "chunk_id": row[0],
            "char_count": row[1],
            "content": row[2],
            "updated_at": row[3],
        }
        for row in rows
    ]


def format_timestamp(value) -> str:
    """Format DB timestamps for display (YYYY-MM-DD HH:MM:SS, no microseconds)."""
    if value is None:
        return ""
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value).split(".")[0].split("+")[0].rstrip("Z")
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
