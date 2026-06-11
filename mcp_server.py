"""MCP server exposing the DATA Pro knowledge base via tools, resources, and prompts."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

from catalog_db import (
    get_domain_stats,
    get_rag_profile,
    list_domains,
    list_sources as catalog_list_sources,
)
from catalog_service import resolve_domain
from db import connect, get_total_chunk_count, list_ingested_sources, search_chunks
from domain_router import route_question
from ingest_service import (
    DEFAULT_DOCS_PATH,
    EMBEDDING_MODEL,
    ingest_files,
    list_available_docs,
    read_file_text,
)
from mcp_registry import (
    get_prompt_meta,
    get_resource_meta,
    get_tool_description,
    is_enabled,
    load_registry,
)

REGISTRY = load_registry()
SERVER = REGISTRY["server"]

MCP_HOST = os.environ.get("MCP_HOST", SERVER.get("host", "0.0.0.0"))
MCP_PORT = int(os.environ.get("MCP_PORT", str(SERVER.get("port", 8000))))
MCP_PATH = os.environ.get("MCP_PATH", SERVER.get("path", "/mcp"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", SERVER.get("transport", "streamable-http"))
MCP_STATELESS = os.environ.get("MCP_STATELESS", str(SERVER.get("stateless", True))).lower() in (
    "1",
    "true",
    "yes",
)

mcp = FastMCP(
    "data-pro",
    instructions=SERVER.get("instructions", ""),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=MCP_STATELESS,
)


@lru_cache(maxsize=1)
def _get_embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


def _serialize_dt(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_resource(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


def _get_source_chunks_from_db(source_file: str) -> list[dict]:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT chunk_id, content, updated_at
            FROM {schema}.knowledge_chunks
            WHERE source_file = :source_file
            ORDER BY chunk_id
            """,
            source_file=source_file,
        )
    finally:
        conn.close()

    return [
        {
            "chunk_id": row[0],
            "text": row[1],
            "updated_at": _serialize_dt(row[2]),
        }
        for row in rows
    ]


def _citation_rules_text() -> str:
    return get_prompt_meta("citation_rules", REGISTRY)["template"]


def _resolve_domain_id(domain: str | None) -> str | None:
    if not domain:
        return None
    row = resolve_domain(domain)
    return row["id"] if row else None


def _search(query: str, top_k: int, domain: str | None = None) -> list[dict]:
    domain_id = _resolve_domain_id(domain)
    chunks = search_chunks(query, _get_embedder(), top_k=top_k, domain_id=domain_id)
    if not chunks and domain_id:
        chunks = search_chunks(query, _get_embedder(), top_k=top_k)
    return chunks


def _build_grounded_prompt(user_question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        [
            f"[{chunk['source_file']} - {chunk['chunk_id']}]\n{chunk['text']}"
            for chunk in chunks
        ]
    )
    template = get_prompt_meta("grounded_answer", REGISTRY)["template"]
    return template.format(
        citation_rules=_citation_rules_text(),
        question=user_question,
        context=context,
    )


def _fetch_chunk(source_file: str, chunk_id: str) -> dict:
    conn, schema = connect()
    try:
        rows = conn.run(
            f"""
            SELECT content, updated_at
            FROM {schema}.knowledge_chunks
            WHERE source_file = :source_file AND chunk_id = :chunk_id
            """,
            source_file=source_file,
            chunk_id=chunk_id,
        )
    finally:
        conn.close()

    if not rows:
        return {"error": f"No chunk found for {source_file!r} / {chunk_id!r}"}

    return {
        "source_file": source_file,
        "chunk_id": chunk_id,
        "text": rows[0][0],
        "updated_at": _serialize_dt(rows[0][1]),
    }


if is_enabled("resources", "ragpro://domains", REGISTRY):
    _domains_meta = get_resource_meta("ragpro://domains", REGISTRY)

    @mcp.resource(
        "ragpro://domains",
        name=_domains_meta["name"],
        description=_domains_meta["description"],
        mime_type=_domains_meta["mime_type"],
    )
    def resource_domains() -> str:
        return _json_resource(list_domains())


if is_enabled("resources", "ragpro://domains/{domain}/sources", REGISTRY):
    _dom_src_meta = get_resource_meta("ragpro://domains/{domain}/sources", REGISTRY)

    @mcp.resource(
        "ragpro://domains/{domain}/sources",
        name=_dom_src_meta["name"],
        description=_dom_src_meta["description"],
        mime_type=_dom_src_meta["mime_type"],
    )
    def resource_domain_sources(domain: str) -> str:
        row = resolve_domain(domain)
        if not row:
            return _json_resource({"error": f"Domain not found: {domain!r}"})
        return _json_resource(catalog_list_sources(domain_id=row["id"]))


if is_enabled("resources", "ragpro://domains/{domain}/stats", REGISTRY):
    _dom_stats_meta = get_resource_meta("ragpro://domains/{domain}/stats", REGISTRY)

    @mcp.resource(
        "ragpro://domains/{domain}/stats",
        name=_dom_stats_meta["name"],
        description=_dom_stats_meta["description"],
        mime_type=_dom_stats_meta["mime_type"],
    )
    def resource_domain_stats(domain: str) -> str:
        row = resolve_domain(domain)
        slug = row["slug"] if row else domain
        return _json_resource(get_domain_stats(slug))


if is_enabled("resources", "ragpro://knowledge-base/stats", REGISTRY):
    _stats_meta = get_resource_meta("ragpro://knowledge-base/stats", REGISTRY)

    @mcp.resource(
        "ragpro://knowledge-base/stats",
        name=_stats_meta["name"],
        description=_stats_meta["description"],
        mime_type=_stats_meta["mime_type"],
    )
    def resource_knowledge_base_stats() -> str:
        sources = list_ingested_sources()
        return _json_resource(
            {
                "total_chunks": get_total_chunk_count(),
                "ingested_source_files": len(sources),
                "embedding_model": EMBEDDING_MODEL,
            }
        )


if is_enabled("resources", "ragpro://knowledge-base/sources", REGISTRY):
    _sources_meta = get_resource_meta("ragpro://knowledge-base/sources", REGISTRY)

    @mcp.resource(
        "ragpro://knowledge-base/sources",
        name=_sources_meta["name"],
        description=_sources_meta["description"],
        mime_type=_sources_meta["mime_type"],
    )
    def resource_ingested_sources() -> str:
        return _json_resource(
            [
                {
                    "source_file": row["source_file"],
                    "chunk_count": row["chunk_count"],
                    "last_ingested": _serialize_dt(row["last_ingested"]),
                }
                for row in list_ingested_sources()
            ]
        )


if is_enabled("resources", "ragpro://chunks/{source_file}/{chunk_id}", REGISTRY):
    _chunk_meta = get_resource_meta("ragpro://chunks/{source_file}/{chunk_id}", REGISTRY)

    @mcp.resource(
        "ragpro://chunks/{source_file}/{chunk_id}",
        name=_chunk_meta["name"],
        description=_chunk_meta["description"],
        mime_type=_chunk_meta["mime_type"],
    )
    def resource_chunk(source_file: str, chunk_id: str) -> str:
        result = _fetch_chunk(source_file, chunk_id)
        return _json_resource(result)


if is_enabled("resources", "ragpro://documents/{source_file}", REGISTRY):
    _doc_meta = get_resource_meta("ragpro://documents/{source_file}", REGISTRY)

    @mcp.resource(
        "ragpro://documents/{source_file}",
        name=_doc_meta["name"],
        description=_doc_meta["description"],
        mime_type=_doc_meta["mime_type"],
    )
    def resource_ingested_document(source_file: str) -> str:
        chunks = _get_source_chunks_from_db(source_file)
        if not chunks:
            return _json_resource(
                {"error": f"No ingested chunks found for source file {source_file!r}"}
            )
        return _json_resource({"source_file": source_file, "chunks": chunks})


if is_enabled("resources", "ragpro://sample-docs/{file_name}", REGISTRY):
    _sample_meta = get_resource_meta("ragpro://sample-docs/{file_name}", REGISTRY)

    @mcp.resource(
        "ragpro://sample-docs/{file_name}",
        name=_sample_meta["name"],
        description=_sample_meta["description"],
        mime_type=_sample_meta["mime_type"],
    )
    def resource_sample_document(file_name: str) -> str:
        file_path = DEFAULT_DOCS_PATH / file_name
        if not file_path.exists():
            raise ValueError(f"Document not found: {file_name}")
        return read_file_text(file_path)


# --- Prompts (reusable templates the client can render with arguments) ---

if is_enabled("prompts", "citation_rules", REGISTRY):
    _citation_meta = get_prompt_meta("citation_rules", REGISTRY)

    @mcp.prompt(
        name="citation_rules",
        description=_citation_meta["description"],
    )
    def prompt_citation_rules() -> str:
        return _citation_meta["template"]


if is_enabled("prompts", "grounded_answer", REGISTRY):
    _grounded_meta = get_prompt_meta("grounded_answer", REGISTRY)

    @mcp.prompt(
        name="grounded_answer",
        description=_grounded_meta["description"],
    )
    def prompt_grounded_answer(question: str, top_k: int = 3) -> str:
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")

        routing = route_question(question, _get_embedder())
        domain_id = routing.get("domain_id")
        chunks = search_chunks(question, _get_embedder(), top_k=top_k, domain_id=domain_id)
        if not chunks and domain_id:
            chunks = search_chunks(question, _get_embedder(), top_k=top_k)
        normalized = [
            {
                "source_file": chunk["source"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "distance": chunk["distance"],
            }
            for chunk in chunks
        ]
        if not normalized:
            return (
                f"{_citation_rules_text()}\n\n"
                f"User question:\n{question}\n\n"
                "Context:\nNo relevant chunks were found in the knowledge base."
            )
        return _build_grounded_prompt(question, normalized)


if is_enabled("prompts", "summarize_document", REGISTRY):
    _summary_meta = get_prompt_meta("summarize_document", REGISTRY)

    @mcp.prompt(
        name="summarize_document",
        description=_summary_meta["description"],
    )
    def prompt_summarize_document(source_file: str) -> str:
        chunks = _get_source_chunks_from_db(source_file)
        if not chunks:
            return (
                f"Summarize the document {source_file!r}.\n\n"
                "No ingested content was found for this file. "
                "Ingest it first via the Source page or ingest_documents tool."
            )

        body = "\n\n".join(
            [f"[{source_file} - {chunk['chunk_id']}]\n{chunk['text']}" for chunk in chunks]
        )
        template = _summary_meta["template"]
        return template.format(source_file=source_file, body=body)


if is_enabled("prompts", "domain_grounded_answer", REGISTRY):
    _dom_grounded_meta = get_prompt_meta("domain_grounded_answer", REGISTRY)

    @mcp.prompt(
        name="domain_grounded_answer",
        description=_dom_grounded_meta["description"],
    )
    def prompt_domain_grounded_answer(question: str, domain: str | None = None, top_k: int = 3) -> str:
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")
        routing = route_question(question, _get_embedder(), domain_override=domain)
        domain_name = routing.get("domain_name") or "General"
        chunks = _search(question, top_k, domain=domain or routing.get("domain_slug"))
        normalized = [
            {
                "source_file": chunk["source"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "distance": chunk["distance"],
            }
            for chunk in chunks
        ]
        if not normalized:
            return (
                f"{_citation_rules_text()}\n\nBusiness domain: {domain_name}\n\n"
                f"User question:\n{question}\n\n"
                "Context:\nNo relevant chunks were found."
            )
        context = "\n\n".join(
            [f"[{c['source_file']} - {c['chunk_id']}]\n{c['text']}" for c in normalized]
        )
        template = _dom_grounded_meta["template"]
        return template.format(
            citation_rules=_citation_rules_text(),
            domain_name=domain_name,
            question=question,
            context=context,
        )


# --- Tools (actions the agent can invoke) ---

if is_enabled("tools", "list_domains", REGISTRY):

    @mcp.tool(description=get_tool_description("list_domains", REGISTRY))
    def list_domains_tool() -> list[dict]:
        """List enabled business domains."""
        return [
            {
                "id": d["id"],
                "slug": d["slug"],
                "name": d["name"],
                "description": d["description"],
            }
            for d in list_domains()
        ]


if is_enabled("tools", "list_domain_sources", REGISTRY):

    @mcp.tool(description=get_tool_description("list_domain_sources", REGISTRY))
    def list_domain_sources(domain: str) -> list[dict]:
        """List data sources under a domain (slug or name)."""
        row = resolve_domain(domain)
        if not row:
            raise ValueError(f"Domain not found: {domain!r}")
        return [
            {
                "id": s["id"],
                "slug": s["slug"],
                "name": s["name"],
                "description": s["description"],
                "source_type": s["source_type"],
                "connector": s["connector"],
            }
            for s in catalog_list_sources(domain_id=row["id"])
        ]


if is_enabled("tools", "get_rag_profile", REGISTRY):

    @mcp.tool(description=get_tool_description("get_rag_profile", REGISTRY))
    def get_rag_profile_tool(source_id: str) -> dict:
        """Return RAG profile for a data source UUID."""
        profile = get_rag_profile(source_id)
        if not profile:
            raise ValueError(f"No RAG profile for source {source_id!r}")
        return profile


if is_enabled("tools", "search_documents", REGISTRY):

    @mcp.tool(description=get_tool_description("search_documents", REGISTRY))
    def search_documents(query: str, top_k: int = 3, domain: str | None = None) -> list[dict]:
        """Semantic search over ingested document chunks. Optional domain filter."""
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")

        chunks = _search(query, top_k, domain=domain)
        return [
            {
                "source_file": chunk["source"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "distance": chunk["distance"],
                "domain_id": chunk.get("domain_id"),
            }
            for chunk in chunks
        ]


if is_enabled("tools", "list_sources", REGISTRY):

    @mcp.tool(description=get_tool_description("list_sources", REGISTRY))
    def list_sources() -> list[dict]:
        """List ingested source files with chunk counts and last-ingested timestamps."""
        return [
            {
                "source_file": row["source_file"],
                "chunk_count": row["chunk_count"],
                "min_chars": row["min_chars"],
                "max_chars": row["max_chars"],
                "last_ingested": _serialize_dt(row["last_ingested"]),
            }
            for row in list_ingested_sources()
        ]


if is_enabled("tools", "get_chunk", REGISTRY):

    @mcp.tool(description=get_tool_description("get_chunk", REGISTRY))
    def get_chunk(source_file: str, chunk_id: str) -> dict:
        """Fetch one chunk by source file name and chunk id (e.g. travel_policy.md / chunk_00)."""
        return _fetch_chunk(source_file, chunk_id)


if is_enabled("tools", "knowledge_base_stats", REGISTRY):

    @mcp.tool(description=get_tool_description("knowledge_base_stats", REGISTRY))
    def knowledge_base_stats() -> dict:
        """Return total chunk count and number of ingested source files."""
        sources = list_ingested_sources()
        return {
            "total_chunks": get_total_chunk_count(),
            "ingested_source_files": len(sources),
            "embedding_model": EMBEDDING_MODEL,
        }


if is_enabled("tools", "list_available_documents", REGISTRY):

    @mcp.tool(description=get_tool_description("list_available_documents", REGISTRY))
    def list_available_documents(docs_path: str = str(DEFAULT_DOCS_PATH)) -> list[dict]:
        """List files on disk that can be ingested (may not yet be in the database)."""
        path = Path(docs_path)
        return [
            {"file_name": file_path.name, "size_bytes": file_path.stat().st_size}
            for file_path in list_available_docs(path)
        ]


if is_enabled("tools", "ingest_documents", REGISTRY):

    @mcp.tool(description=get_tool_description("ingest_documents", REGISTRY))
    def ingest_documents(
        file_names: list[str],
        docs_path: str = str(DEFAULT_DOCS_PATH),
    ) -> dict:
        """Ingest documents from sample_docs (or docs_path) into the knowledge base."""
        if not file_names:
            raise ValueError("file_names must contain at least one file name")

        path = Path(docs_path)
        targets = [path / name for name in file_names]
        missing = [name for name, target in zip(file_names, targets) if not target.exists()]
        if missing:
            raise ValueError(f"File(s) not found under {path}: {', '.join(missing)}")

        report = ingest_files(targets, _get_embedder(), replace_existing=True)
        return {
            "total_chunks": report["total_chunks"],
            "deleted_chunks": report["deleted_chunks"],
            "files": report["files"],
            "errors": report["errors"],
        }


def main() -> None:
    if MCP_TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    elif MCP_TRANSPORT == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
