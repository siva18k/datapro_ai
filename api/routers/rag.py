from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_embedder
from catalog_db import get_rag_profile, get_source, update_rag_profile
from catalog_rag_service import index_structured_catalog
from catalog_service import ingest_source_files, list_source_files

router = APIRouter(prefix="/rag", tags=["rag"])


class RagProfileUpdate(BaseModel):
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    instructions: str | None = None
    metadata_text: str | None = None


@router.get("/sources/{source_id}")
def get_profile(source_id: str):
    source = get_source(source_id=source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    profile = get_rag_profile(source_id)
    if not profile:
        raise HTTPException(404, "RAG profile not found")
    return {"source": source, "profile": profile}


@router.patch("/sources/{source_id}")
def patch_profile(source_id: str, body: RagProfileUpdate):
    if not get_rag_profile(source_id):
        raise HTTPException(404, "RAG profile not found")
    update_rag_profile(source_id, **body.model_dump(exclude_none=True))
    return get_rag_profile(source_id)


@router.post("/sources/{source_id}/index-catalog")
def index_catalog(source_id: str):
    """Ingest & embed catalog metadata (+ lookup table rows) for a structured postgres dataset."""
    source = get_source(source_id=source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    if source.get("source_type") != "structured":
        raise HTTPException(400, "Catalog indexing is for structured datasets only")
    try:
        return index_structured_catalog(source, get_embedder())
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/sources/{source_id}/reingest")
def reingest(source_id: str):
    source = get_source(source_id=source_id)
    if not source:
        raise HTTPException(404, "Source not found")

    if source.get("source_type") == "structured":
        try:
            return index_structured_catalog(source, get_embedder())
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc

    files = list_source_files(source)
    if not files:
        return {"total_chunks": 0, "files": [], "errors": [], "catalog_chunks": 0}
    return ingest_source_files(source, files, get_embedder())
