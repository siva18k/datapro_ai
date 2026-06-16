"""Shared dependencies (embedder, catalog init)."""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from catalog_service import ensure_catalog_ready
from settings_service import get_embedding_model, scrub_invalid_managed_settings


@lru_cache(maxsize=4)
def _load_embedder(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def get_embedder() -> SentenceTransformer:
    return _load_embedder(get_embedding_model())


def clear_embedder_cache() -> None:
    _load_embedder.cache_clear()


def bootstrap() -> None:
    scrub_invalid_managed_settings()
    ensure_catalog_ready()
    # Warm routing metadata so first Ask/Analytics request does not block on catalog scans.
    from routing_cache import get_cached_routing_context

    get_cached_routing_context()
