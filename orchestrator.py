"""Domain-aware retrieval orchestration for Ask and API.

Unstructured path: vector search over knowledge_chunks (today).
Structured path: structured_orchestrator.py (SQL on postgres).
Python curation: code_orchestrator.py (CSV/files — filter/aggregate before answer LLM).
"""

from __future__ import annotations

import re
from typing import Any

from catalog_db import get_domain, list_sources
from catalog_service import ensure_catalog_ready
from db import search_chunks
from api.answer_format import CHAT_RESPONSE_FORMAT
from mcp_client import get_default_mcp_url
from mcp_client import search_documents as mcp_search_documents
from query_planner import resolve_query_plan


def retrieve_for_question(
    question: str,
    embedder,
    top_k: int = 3,
    *,
    use_mcp: bool = False,
    mcp_url: str | None = None,
    domain_override: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Route to a domain and retrieve relevant chunks."""
    ensure_catalog_ready()
    plan = resolve_query_plan(
        question, embedder, domain_override=domain_override
    )
    routing = plan.routing
    domain_id = plan.domain_id

    meta: dict[str, Any] = {
        "routing": routing,
        "domain_id": domain_id,
        "domain_name": plan.domain_name,
        "retrieval_mode": "mcp" if use_mcp else "direct",
        "execution_kind": plan.execution_kind,
        "query_kind": _legacy_query_kind(plan.execution_kind),
        "source_id": plan.source_id,
        "source_name": plan.source_name,
    }

    if use_mcp:
        url = mcp_url or get_default_mcp_url()
        domain_arg = routing.get("domain_slug") or routing.get("domain_name")
        chunks = mcp_search_documents(
            url,
            question,
            top_k=top_k,
            domain=domain_arg if domain_id else None,
        )
        meta["mcp_url"] = url
        meta["mcp_tool"] = "search_documents"
        return chunks, meta

    chunks = search_chunks(
        question,
        embedder,
        top_k=top_k,
        domain_id=domain_id,
    )

    if not chunks and domain_id:
        chunks = search_chunks(question, embedder, top_k=top_k)
        meta["fallback"] = "searched_all_domains"

    return chunks, meta


def retrieve_for_question_with_debug(
    question: str,
    embedder,
    top_k: int = 3,
    *,
    use_mcp: bool = False,
    mcp_url: str | None = None,
    domain_override: str | None = None,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> dict[str, Any]:
    query_vector = embedder.encode([question])[0]
    chunks, meta = retrieve_for_question(
        question,
        embedder,
        top_k=top_k,
        use_mcp=use_mcp,
        mcp_url=mcp_url,
        domain_override=domain_override,
    )
    routing = meta.get("routing", {})
    return {
        "retrieval_mode": meta.get("retrieval_mode", "direct"),
        "routing": routing,
        "domain_id": meta.get("domain_id"),
        "domain_name": meta.get("domain_name"),
        "domain_slug": routing.get("domain_slug"),
        "routing_confidence": routing.get("confidence"),
        "routing_method": routing.get("method"),
        "fallback": meta.get("fallback"),
        "mcp_url": meta.get("mcp_url"),
        "mcp_tool": meta.get("mcp_tool"),
        "embedding_model": embedding_model if not use_mcp else f"via MCP ({embedding_model})",
        "embedding_dimensions": len(query_vector),
        "embedding_preview": [round(float(v), 6) for v in query_vector[:8]],
        "chunks": chunks,
    }


_SOURCE_CITATION_RE = re.compile(r"\s*\[[^\]]+ - [^\]]+\]")


def strip_source_citations(text: str) -> str:
    """Remove inline [source_file - chunk_id] citations from LLM answers."""
    cleaned = _SOURCE_CITATION_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def build_domain_rag_prompt(
    user_question: str,
    chunks: list[dict],
    *,
    domain_name: str | None = None,
    cite_sources: bool = False,
) -> tuple[str, str]:
    context = "\n\n".join(
        [f"[{c['source']} - {c['chunk_id']}]\n{c['text']}" for c in chunks]
    )
    domain_line = f"Business domain: {domain_name}\n" if domain_name else ""
    citation_line = (
        "Cite the sources in the format [source_file - chunk_id].\n"
        if cite_sources
        else "Do not include source paths or chunk IDs in your answer; sources are tracked separately.\n"
    )
    llm_prompt = f"""You are an internal knowledge assistant in a chat conversation.
{domain_line}Answer only from the provided context.
If the answer is not supported by the context, say:
"I do not know based on the provided documents."
{citation_line}
{CHAT_RESPONSE_FORMAT}

User question:
{user_question}

Context:
{context}
"""
    return context, llm_prompt


def get_domain_source_ids(domain_id: str) -> list[str]:
    return [s["id"] for s in list_sources(domain_id=domain_id)]


def _legacy_query_kind(execution_kind: str) -> str:
    """Map execution_kind to API field query_kind for clients."""
    if execution_kind == "rag":
        return "unstructured"
    if execution_kind == "sql":
        return "structured"
    return execution_kind  # python | hybrid
