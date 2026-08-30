"""Shared dependencies (embedder, catalog init).

This module uses a lightweight Mistral-based embedder.
"""

from __future__ import annotations

from functools import lru_cache
import os
import time

import certifi
import requests

from catalog_service import ensure_catalog_ready
from settings_service import get_embedding_model, scrub_invalid_managed_settings, get_api_key


def _resolve_mistral_tls_verify() -> str | bool:
    """Return requests verify value for Mistral API calls.

    Priority:
    1) MISTRAL_TLS_INSECURE=1/true/yes/on -> False (last-resort local workaround)
    2) REQUESTS_CA_BUNDLE
    3) SSL_CERT_FILE
    4) certifi bundle
    """
    insecure_flag = (os.environ.get("MISTRAL_TLS_INSECURE") or "").strip().lower()
    if insecure_flag in {"1", "true", "yes", "on"}:
        return False
    ca_bundle = (os.environ.get("REQUESTS_CA_BUNDLE") or "").strip()
    if ca_bundle:
        return ca_bundle
    ssl_cert_file = (os.environ.get("SSL_CERT_FILE") or "").strip()
    if ssl_cert_file:
        return ssl_cert_file
    return certifi.where()


@lru_cache(maxsize=4)
class MistralEmbedder:
    """Simple embedder that calls the Mistral embeddings endpoint.

    Provides an `encode(list[str]) -> list[list[float]]` method used across ingestion and retrieval.
    """

    def __init__(self, model_name: str | None = None):
        self.model = model_name or get_embedding_model()
        if not self.model.startswith("mistral-embed"):
            raise RuntimeError(
                "Only Mistral embedding models are supported. "
                "Set EMBEDDING_MODEL to mistral-embed-1 or mistral-embed-2312 in Settings."
            )

    def encode(self, texts: list[str]) -> list[list[float]]:
        api_key = get_api_key("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is not set (Settings → LLM)")
        url = "https://api.mistral.ai/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": texts}
        verify_bundle = _resolve_mistral_tls_verify()
        max_attempts = 5
        r = None
        for attempt in range(max_attempts):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=60, verify=verify_bundle)
            except requests.exceptions.SSLError as exc:
                raise RuntimeError(
                    "TLS certificate verification failed contacting Mistral embeddings. "
                    "Set REQUESTS_CA_BUNDLE (or SSL_CERT_FILE) in .env to your CA bundle path. "
                    "Temporary local workaround: set MISTRAL_TLS_INSECURE=1."
                ) from exc

            if r.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else float(2**attempt)
                except ValueError:
                    delay = float(2**attempt)
                time.sleep(min(max(delay, 0.25), 8.0))
                continue
            break

        if r is None:
            raise RuntimeError("Embedding request failed before receiving a response")
        r.raise_for_status()
        data = r.json()
        # Try common response shapes: data.data[*].embedding or embeddings
        out: list[list[float]] = []
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            for item in data["data"]:
                vec = item.get("embedding") or item.get("embeddings") or item.get("vector")
                if not isinstance(vec, list):
                    raise RuntimeError("Unexpected embedding payload from Mistral")
                out.append([float(x) for x in vec])
            return out
        if isinstance(data, dict) and isinstance(data.get("embeddings"), list):
            for vec in data.get("embeddings"):
                out.append([float(x) for x in vec])
            return out
        raise RuntimeError("Unrecognized embeddings response from Mistral: %s" % (str(data)))


@lru_cache(maxsize=4)
def _load_embedder(model_name: str) -> MistralEmbedder:
    return MistralEmbedder(model_name)


def get_embedder(model_name: str | None = None) -> MistralEmbedder:
    return _load_embedder(model_name or get_embedding_model())


def clear_embedder_cache() -> None:
    _load_embedder.cache_clear()


def bootstrap() -> None:
    scrub_invalid_managed_settings()
    try:
        ensure_catalog_ready()
    except Exception as exc:
        # Keep API startup available even if catalog DB is temporarily unavailable.
        print(f"[bootstrap] catalog init skipped: {exc}")
        return

    # Warm routing metadata so first Ask/Analytics request does not block on catalog scans.
    try:
        from routing_cache import get_cached_routing_context

        get_cached_routing_context()
    except Exception as exc:
        print(f"[bootstrap] routing warmup skipped: {exc}")
