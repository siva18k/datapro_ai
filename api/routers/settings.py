from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from settings_service import get_public_settings, save_settings, test_database_connection

from db import connect, vector_literal, knowledge_chunks_has_embedding_model_column
from api.deps import get_embedder
from settings_service import get_embedding_model

router = APIRouter(prefix="/settings", tags=["settings"])


class DatabaseSettings(BaseModel):
    use_database_url: bool = False
    database_url: str = ""
    host: str = ""
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    schema: str = "ragpro"
    sslmode: str = "require"


class LlmSettings(BaseModel):
    default_backend: str | None = None
    default_model: str | None = None
    ollama_base_url: str | None = None
    mistral_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None


class AskSettings(BaseModel):
    conversation_turns: int | None = Field(default=None, ge=0, le=20)


class SettingsUpdate(BaseModel):
    database: DatabaseSettings | None = None
    mcp_url: str | None = None
    embedding_model: str | None = None
    ask: AskSettings | None = None
    llm: LlmSettings | None = None
    # Legacy top-level key
    mistral_api_key: str | None = None


class TestDatabaseBody(BaseModel):
    database: DatabaseSettings


@router.get("")
def get_settings():
    return get_public_settings()


@router.put("")
def put_settings(body: SettingsUpdate):
    try:
        return save_settings(body.model_dump(exclude_none=True))
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/test-database")
def test_db(body: TestDatabaseBody | None = None):
    overrides = body.model_dump() if body else None
    ok, message = test_database_connection(overrides)
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}


class ReRagBody(BaseModel):
    embedding_model: str | None = None


class MetadataRagStatusRow(BaseModel):
    source_file: str
    chunk_id: str
    embedded: bool
    embedding_model: str | None = None
    updated_at: str | None = None


class MetadataRagStatus(BaseModel):
    total: int
    embedded: int
    missing: int
    rows: list[MetadataRagStatusRow]


class ReRagResponse(BaseModel):
    updated: int
    summary: str
    status: MetadataRagStatus


def _load_metadata_rag_status(conn, schema: str) -> dict:
    has_embedding_model = knowledge_chunks_has_embedding_model_column()
    embedding_model_col = "embedding_model" if has_embedding_model else "NULL::text AS embedding_model"
    rows = conn.run(
        f"""
        SELECT source_file, chunk_id, embedding IS NOT NULL AS embedded, {embedding_model_col}, updated_at
        FROM {schema}.knowledge_chunks
        WHERE source_file LIKE :m1 OR source_file LIKE :m2
        ORDER BY source_file, chunk_id
        """,
        m1="%_instructions",
        m2="%_metadata",
    )
    total = len(rows)
    embedded = sum(1 for row in rows if bool(row[2]))
    return {
        "total": total,
        "embedded": embedded,
        "missing": total - embedded,
        "rows": [
            {
                "source_file": row[0],
                "chunk_id": row[1],
                "embedded": bool(row[2]),
                "embedding_model": row[3],
                "updated_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ],
    }


@router.get("/metadata-rag-status", response_model=MetadataRagStatus)
def metadata_rag_status():
    try:
        conn, schema = connect()
    except Exception as exc:
        raise HTTPException(500, f"DB connection failed: {exc}") from exc

    try:
        return _load_metadata_rag_status(conn, schema)
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.post("/re-rag", response_model=ReRagResponse)
def re_rag_metadata(body: ReRagBody | None = None):
    """Recompute embeddings for application metadata chunks (instructions/metadata).

    Runs in the request thread but schedules no long background work; this function
    performs batched updates and returns the number of updated chunks.
    """
    try:
        conn, schema = connect()
    except Exception as exc:
        raise HTTPException(500, f"DB connection failed: {exc}") from exc

    try:
        rows = conn.run(
            f"""
            SELECT id::text, content
            FROM {schema}.knowledge_chunks
            WHERE source_file LIKE :m1 OR source_file LIKE :m2
            ORDER BY id
            """,
            m1="%_instructions",
            m2="%_metadata",
        )
        if not rows:
            status = _load_metadata_rag_status(conn, schema)
            return {
                "updated": 0,
                "summary": "No metadata chunks found.",
                "status": status,
            }

        model_name = body.embedding_model if body is not None else None
        embedder = get_embedder(model_name=model_name)
        batch_size = 64
        updated = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            ids = [row[0] for row in batch]
            texts = [row[1] for row in batch]
            try:
                vectors = embedder.encode(texts)
            except Exception as exc:
                raise HTTPException(500, f"Embedding failed: {exc}") from exc

            embedding_model = model_name or get_embedding_model()
            has_embedding_model = knowledge_chunks_has_embedding_model_column()
            for rid, vec in zip(ids, vectors):
                emb = vector_literal(vec)
                if has_embedding_model:
                    try:
                        conn.run(
                            f"""
                            UPDATE {schema}.knowledge_chunks
                            SET embedding = :embedding::vector,
                                embedding_model = :embedding_model,
                                updated_at = now()
                            WHERE id = :id
                            """,
                            embedding=emb,
                            embedding_model=embedding_model,
                            id=rid,
                        )
                    except Exception as exc:
                        msg = str(exc)
                        if "different vector dimensions" in msg:
                            raise HTTPException(
                                500,
                                "Embedding column dimension mismatch. "
                                "Run migration 015_embedding_vector_unbounded.sql and ensure "
                                "the ANN index `ix_knowledge_chunks_embedding_cosine` is dropped "
                                "during transition, then retry recompute.",
                            ) from exc
                        raise HTTPException(500, f"Failed updating metadata chunk {rid}: {msg}") from exc
                else:
                    try:
                        conn.run(
                            f"""
                            UPDATE {schema}.knowledge_chunks
                            SET embedding = :embedding::vector, updated_at = now()
                            WHERE id = :id
                            """,
                            embedding=emb,
                            id=rid,
                        )
                    except Exception as exc:
                        msg = str(exc)
                        if "different vector dimensions" in msg:
                            raise HTTPException(
                                500,
                                "Embedding column dimension mismatch. "
                                "Run migration 015_embedding_vector_unbounded.sql and ensure "
                                "the ANN index `ix_knowledge_chunks_embedding_cosine` is dropped "
                                "during transition, then retry recompute.",
                            ) from exc
                        raise HTTPException(500, f"Failed updating metadata chunk {rid}: {msg}") from exc
                updated += 1

        status = _load_metadata_rag_status(conn, schema)
        return {
            "updated": updated,
            "summary": (
                f"Metadata RAG recompute complete: {updated} updated, "
                f"{status['embedded']}/{status['total']} embedded, {status['missing']} missing."
            ),
            "status": status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Metadata recompute failed: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
