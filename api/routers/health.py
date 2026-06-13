from fastapi import APIRouter

from catalog_db import list_domains, list_sources
from db import get_total_chunk_count, list_ingested_sources
from readiness_service import check_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/readiness")
def readiness():
    return check_readiness()


@router.get("/stats")
def stats():
    return {
        "total_chunks": get_total_chunk_count(),
        "ingested_files": len(list_ingested_sources()),
        "domain_count": len(list_domains(enabled_only=False)),
        "dataset_count": len(list_sources(enabled_only=False)),
    }
