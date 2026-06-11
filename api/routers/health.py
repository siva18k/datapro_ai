from fastapi import APIRouter

from db import get_total_chunk_count, list_ingested_sources

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/stats")
def stats():
    return {
        "total_chunks": get_total_chunk_count(),
        "ingested_files": len(list_ingested_sources()),
    }
