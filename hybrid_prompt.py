"""Blend RAG retrieval with catalog definitions for SQL / Python generation."""

from __future__ import annotations

from typing import Any

MAX_PROMPT_CHUNKS = 6
MAX_CHUNK_CHARS = 900

CATALOG_META_PREFIX = "catalog_meta/"


def _chunk_source(chunk: dict[str, Any]) -> str:
    return str(chunk.get("source") or chunk.get("source_file") or "unknown")


def is_catalog_metadata_chunk(chunk: dict[str, Any]) -> bool:
    return _chunk_source(chunk).startswith(CATALOG_META_PREFIX)


def format_rag_chunks_for_prompt(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""
    lines: list[str] = []
    for index, chunk in enumerate(chunks[:MAX_PROMPT_CHUNKS], 1):
        source = _chunk_source(chunk)
        chunk_id = chunk.get("chunk_id", "")
        kind = "catalog metadata" if is_catalog_metadata_chunk(chunk) else "document"
        text = (chunk.get("text") or "").strip()
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS] + "…"
        lines.append(
            f"### Retrieved {index} ({kind}) — `{source}` / `{chunk_id}`\n{text}"
        )
    return "\n\n".join(lines)


def build_sql_rag_supplement(chunks: list[dict[str, Any]] | None) -> str:
    """Extra instructions + chunk text for text-to-SQL prompts."""
    if not chunks:
        return (
            "## Retrieval note\n"
            "No ingested catalog embeddings or documents matched this question.\n"
            "Rely on **Dataset definition** (join paths, hub/bridge tables, caveats) and "
            "**Column reference** (exact names and types) as the authoritative schema context."
        )
    body = format_rag_chunks_for_prompt(chunks)
    catalog_count = sum(1 for c in chunks if is_catalog_metadata_chunk(c))
    doc_count = len(chunks) - catalog_count
    parts = []
    if catalog_count:
        parts.append(f"{catalog_count} catalog metadata chunk(s)")
    if doc_count:
        parts.append(f"{doc_count} document chunk(s)")
    summary = " and ".join(parts) if parts else f"{len(chunks)} chunk(s)"
    return (
        "## Retrieved context (ingested RAG)\n"
        f"Found {summary}. Use this to interpret business terms, naming, and domain language.\n"
        "For SQL identifiers and joins, **Allowed tables**, **Dataset definition**, and "
        "**Column reference** still override narrative text in retrieved chunks.\n\n"
        f"{body}"
    )


def build_python_rag_supplement(chunks: list[dict[str, Any]] | None) -> str:
    """Extra instructions for Python curation over files."""
    if not chunks:
        return (
            "## Retrieval note\n"
            "No ingested document chunks matched this question.\n"
            "Rely on the **Dataset definition** and **Files** list below to choose inputs and columns."
        )
    body = format_rag_chunks_for_prompt(chunks)
    return (
        "## Retrieved context (ingested documents)\n"
        "Use this to interpret the question and choose relevant files/columns. "
        "Read only files listed under **Files** that match the question.\n\n"
        f"{body}"
    )


def retrieve_hybrid_chunks(
    question: str,
    embedder,
    *,
    domain_id: str | None,
    source_id: str | None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Vector search scoped to dataset, then domain, for generation-time context."""
    from db import search_chunks

    chunks: list[dict[str, Any]] = []
    if source_id:
        chunks = search_chunks(question, embedder, top_k=top_k, source_id=source_id)
    if not chunks and domain_id:
        chunks = search_chunks(question, embedder, top_k=top_k, domain_id=domain_id)
    return chunks


def prioritize_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Catalog metadata chunks first — best grounding for structured SQL."""
    catalog = [c for c in chunks if is_catalog_metadata_chunk(c)]
    docs = [c for c in chunks if not is_catalog_metadata_chunk(c)]
    return (catalog + docs)[:MAX_PROMPT_CHUNKS]


def merge_generation_supplements(*parts: str) -> str:
    """Join RAG and MCP supplement blocks for text-to-SQL / Python prompts."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
