"""Ask pipeline with step-by-step status events for streaming UI."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from api.answer_format import build_sql_summary_prompt
from api.llm import generate_answer, resolve_llm_runtime
from catalog_service import ensure_catalog_ready
from db import search_chunks
from mcp_client import get_default_mcp_url
from mcp_client import search_documents as mcp_search_documents
from orchestrator import build_domain_rag_prompt, strip_source_citations, _legacy_query_kind
from query_planner import find_best_rag_domain, resolve_query_plan, structured_fallback_available
from structured_orchestrator import generate_and_execute_readonly_sql, plan_structured_query

from api.ask_models import AskRequest, AskResponse, SourceChunk


def _status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def _result(response: AskResponse) -> dict[str, Any]:
    return {"type": "result", "data": response.model_dump()}


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def run_ask_events(body: AskRequest, embedder) -> Iterator[dict[str, Any]]:
    """Yield status events, then a single result event (or error)."""
    ensure_catalog_ready()
    llm_backend, llm_model, llm_base_url = resolve_llm_runtime(
        backend=body.backend,
        model=body.model,
        base_url=body.ollama_base_url,
    )

    yield _status("Routing question to the best domain and dataset…")
    plan = resolve_query_plan(body.question, embedder, domain_override=body.domain_override)
    routing = plan.routing
    method = routing.get("method", "")

    if method == "override" and plan.domain_name:
        yield _status(f"Using {plan.domain_name} domain (your selection).")
    elif plan.domain_name:
        yield _status(f"Matched {plan.domain_name} domain.")
    else:
        yield _status("No single domain match — searching all domains.")

    for note in plan.notes:
        yield _status(note)

    if plan.source_name and plan.execution_kind in ("sql", "hybrid"):
        yield _status(f"Selected dataset «{plan.source_name}» ({plan.execution_kind.upper()} path).")

    meta: dict[str, Any] = {
        "routing": routing,
        "domain_id": plan.domain_id,
        "domain_name": plan.domain_name,
        "execution_kind": plan.execution_kind,
        "query_kind": _legacy_query_kind(plan.execution_kind),
        "source_id": plan.source_id,
        "source_name": plan.source_name,
    }

    llm = (llm_backend, llm_model, llm_base_url)

    if plan.execution_kind in ("sql", "hybrid"):
        yield from _structured_events(body, embedder, meta, llm)
        return

    yield from _rag_events(body, embedder, meta, llm)


def _structured_events(
    body: AskRequest,
    embedder,
    meta: dict[str, Any],
    llm: tuple[str, str, str],
) -> Iterator[dict[str, Any]]:
    llm_backend, llm_model, llm_base_url = llm
    routing = meta.get("routing") or {}
    domain_name = meta.get("domain_name")
    execution_kind = meta.get("execution_kind")

    yield _status("Loading catalog metadata from database…")
    plan = plan_structured_query(
        body.question,
        embedder,
        domain_override=body.domain_override,
        routing=routing,
        domain_id=meta.get("domain_id"),
        force_structured=True,
    )
    if not plan:
        yield _status("Structured query not applicable — searching documents instead…")
        yield from _rag_events(body, embedder, meta, llm)
        return

    ctx = plan.schema_context
    table_count = len(ctx.tables)
    yield _status(f"Using dataset «{ctx.source_name}» ({table_count} cataloged tables).")

    yield _status("Generating SQL from schema definitions…")

    try:
        plan.sql, columns, rows, sql_notes = generate_and_execute_readonly_sql(
            body.question,
            plan.source_id,
            ctx,
            model=llm_model,
            backend=llm_backend,
            base_url=llm_base_url,
        )
        yield _status("Running read-only query on the database…")
    except Exception as exc:
        if execution_kind == "sql":
            yield _result(
                AskResponse(
                    answer=f"I could not query the database for this question: {exc}",
                    domain_name=domain_name,
                    routing_method=routing.get("method"),
                    routing_confidence=routing.get("confidence"),
                    query_kind="structured",
                    sources=[],
                )
            )
            return
        yield _status("Database query failed — searching documents instead…")
        yield from _rag_events(body, embedder, meta, llm)
        return

    row_count = len(rows)
    yield _status(
        f"Retrieved {row_count} row{'s' if row_count != 1 else ''} — summarizing answer…"
    )

    summary_prompt = build_sql_summary_prompt(
        question=body.question,
        columns=columns,
        rows=rows,
    )
    answer = generate_answer(
        summary_prompt,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    if sql_notes:
        answer = f"{answer}\n\n**Note:** " + " ".join(sql_notes)

    sources = [
        SourceChunk(
            source=f"sql:{ctx.source_name}",
            chunk_id="query",
            text=plan.sql,
        )
    ]

    if execution_kind == "hybrid":
        yield _status("Also searching ingested documents…")
        for event in _rag_search_events(body, embedder, meta):
            if event["type"] == "status":
                yield event
            elif event["type"] == "_chunks":
                chunks = event["chunks"]
                if chunks:
                    doc_context, _ = build_domain_rag_prompt(
                        f"{body.question}\n\nSupplement with document context if helpful.",
                        chunks,
                        domain_name=domain_name,
                        cite_sources=body.debug,
                    )
                    yield _status("Blending database results with document context…")
                    answer = generate_answer(
                        f"{summary_prompt}\n\nAdditional document context:\n{doc_context}",
                        model=llm_model,
                        backend=llm_backend,
                        base_url=llm_base_url,
                    )
                    sources.extend(
                        SourceChunk(
                            source=c.get("source", c.get("source_file", "")),
                            chunk_id=c.get("chunk_id", ""),
                            text=c.get("text", ""),
                            distance=c.get("distance"),
                        )
                        for c in chunks
                    )
                break

    if not body.debug:
        answer = strip_source_citations(answer)

    yield _result(
        AskResponse(
            answer=answer,
            question=body.question,
            domain_name=domain_name,
            routing_method=routing.get("method"),
            routing_confidence=routing.get("confidence"),
            query_kind="structured" if execution_kind == "sql" else "hybrid",
            sources=sources,
            sql=plan.sql,
            columns=columns,
            rows=rows,
        )
    )


def _rag_search_events(
    body: AskRequest,
    embedder,
    meta: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Search chunks; final event is internal _chunks payload."""
    domain_id = meta.get("domain_id")
    if body.use_mcp:
        yield _status("Searching documents via MCP server…")
        url = body.mcp_url or get_default_mcp_url()
        domain_arg = meta.get("routing", {}).get("domain_slug") or meta.get("domain_name")
        chunks = mcp_search_documents(
            url,
            body.question,
            top_k=body.top_k,
            domain=domain_arg if domain_id else None,
        )
    else:
        yield _status(f"Searching ingested documents (top {body.top_k} chunks)…")
        chunks = search_chunks(
            body.question,
            embedder,
            top_k=body.top_k,
            domain_id=domain_id,
        )
        if not chunks:
            yield _status("No chunks in this domain — searching other domains…")
            best_domain, chunks = find_best_rag_domain(
                body.question, embedder, top_k=body.top_k, prefer_domain_id=domain_id
            )
            if best_domain and best_domain["id"] != domain_id:
                meta["domain_id"] = best_domain["id"]
                meta["domain_name"] = best_domain["name"]
                meta["routing"] = {
                    **(meta.get("routing") or {}),
                    "domain_id": best_domain["id"],
                    "domain_name": best_domain["name"],
                    "domain_slug": best_domain.get("slug"),
                }
                yield _status(f"Found relevant documents in {best_domain['name']} domain.")

    if chunks:
        yield _status(f"Found {len(chunks)} relevant chunk(s).")
    yield {"type": "_chunks", "chunks": chunks}


def _rag_events(
    body: AskRequest,
    embedder,
    meta: dict[str, Any],
    llm: tuple[str, str, str],
) -> Iterator[dict[str, Any]]:
    llm_backend, llm_model, llm_base_url = llm
    routing = meta.get("routing") or {}
    domain_name = meta.get("domain_name")

    chunks: list[dict] = []
    for event in _rag_search_events(body, embedder, meta):
        if event["type"] == "status":
            yield event
        elif event["type"] == "_chunks":
            chunks = event["chunks"]

    if not chunks:
        fallback = structured_fallback_available(body.question, embedder)
        if fallback and not body.domain_override:
            for note in fallback.notes:
                yield _status(note)
            meta["domain_id"] = fallback.domain_id
            meta["domain_name"] = fallback.domain_name
            meta["execution_kind"] = "sql"
            meta["query_kind"] = "structured"
            meta["routing"] = fallback.routing
            yield from _structured_events(body, embedder, meta, llm)
            return

        from catalog_db import list_sources

        structured = (
            list_sources(domain_id=meta.get("domain_id"), source_type="structured", enabled_only=True)
            if meta.get("domain_id")
            else []
        )
        if structured:
            yield _status("No catalog embeddings found for this domain yet.")
            yield _result(
                AskResponse(
                    answer=(
                        "I could not find embedded catalog metadata for this question. "
                        "Try rephrasing as an analytical question (counts, totals, lists) to run SQL, "
                        "or open **RAG** → select the dataset → **Ingest & embed catalog**."
                    ),
                    domain_name=domain_name,
                    routing_method=routing.get("method"),
                    routing_confidence=routing.get("confidence"),
                    query_kind=meta.get("query_kind"),
                    sources=[],
                )
            )
            return

        yield _status("No matching documents found in any domain.")
        yield _result(
            AskResponse(
                answer="I do not know based on the provided documents.",
                domain_name=domain_name,
                routing_method=routing.get("method"),
                routing_confidence=routing.get("confidence"),
                query_kind=meta.get("query_kind"),
                sources=[],
            )
        )
        return

    yield _status("Generating answer from document context…")
    domain_name = meta.get("domain_name") or domain_name
    _, prompt = build_domain_rag_prompt(
        body.question,
        chunks,
        domain_name=domain_name,
        cite_sources=body.debug,
    )
    answer = generate_answer(
        prompt,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    if not body.debug:
        answer = strip_source_citations(answer)

    sources = [
        SourceChunk(
            source=c.get("source", c.get("source_file", "")),
            chunk_id=c.get("chunk_id", ""),
            text=c.get("text", ""),
            distance=c.get("distance"),
        )
        for c in chunks
    ]
    yield _result(
        AskResponse(
            answer=answer,
            question=body.question,
            domain_name=domain_name,
            routing_method=routing.get("method"),
            routing_confidence=routing.get("confidence"),
            query_kind=meta.get("query_kind"),
            sources=sources,
        )
    )


def collect_ask_response(body: AskRequest, embedder) -> AskResponse:
    """Run pipeline and return final AskResponse (non-streaming)."""
    response: AskResponse | None = None
    for event in run_ask_events(body, embedder):
        if event["type"] == "result":
            response = AskResponse(**event["data"])
        elif event["type"] == "error":
            raise RuntimeError(event["message"])
    if response is None:
        raise RuntimeError("Ask pipeline produced no response")
    return response
