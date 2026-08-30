"""Ask pipeline with step-by-step status events for streaming UI."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from api.answer_format import build_sql_summary_prompt
from api.llm import generate_answer, resolve_llm_runtime
from catalog_service import ensure_catalog_ready, normalize_domain_overrides
from db import chunk_verify_sql, search_chunks
from mcp_domain_service import retrieve_chunks_for_scope
from hybrid_prompt import merge_generation_supplements, prioritize_chunks
from catalog_rag_service import filter_chunks_to_rag_selection
from mcp_ask_planner import (
    execute_mcp_enrichment,
    format_mcp_context_supplement,
    has_domain_mcp_bindings,
    plan_mcp_enrichment,
    resolve_domain_slug,
)
from orchestrator import build_attachment_answer_prompt, build_domain_rag_prompt, strip_source_citations, _legacy_query_kind
from query_planner import coerce_to_sql_plan, resolve_query_plan, structured_fallback_available
from scope_resolver import chunk_source_files_for_scope
from structured_orchestrator import (
    generate_and_execute_readonly_sql,
    load_table_business_rules_for_domain,
    plan_structured_query,
)

from api.ask_models import (
    AskRequest,
    AskResponse,
    PipelineChunkRef,
    PipelineTraceDetail,
    PipelineTraceStep,
    SourceChunk,
)
from conversation_context import (
    ATTACHED_DOCS_MARKER,
    contextual_question_with_history,
    has_attached_documents,
    retrieval_query_with_history,
    select_relevant_attachment_content,
    split_attached_documents,
    truncate_history,
)
from conversation_session import prepare_session_context
from temporal_context import format_query_results_with_time_context


def _conversation_history(body: AskRequest) -> list[dict[str, Any]]:
    raw = [
        {
            "role": t.role,
            "content": t.content,
            **({"question": t.question} if t.question else {}),
            **({"sql": t.sql} if t.sql else {}),
            **({"columns": t.columns} if t.columns else {}),
            **({"rows": t.rows} if t.rows is not None else {}),
        }
        for t in body.conversation_history
    ]
    return truncate_history(raw)


def _retrieval_query(body: AskRequest, history: list[dict[str, Any]] | None = None) -> str:
    h = history if history is not None else _conversation_history(body)
    chat = [{"role": t["role"], "content": t["content"]} for t in h if t.get("content")]
    return retrieval_query_with_history(body.question, chat)


def _session_fields(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_reset": bool(meta.get("session_reset")),
        "session_summary": meta.get("session_summary"),
        "new_topic": bool(meta.get("new_topic")),
    }


def _meta_history(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return meta.get("conversation_history") or []


def _status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def _trace_event(body: AskRequest, message: str, phase: str, **detail: Any) -> dict[str, Any]:
    cleaned = {k: v for k, v in detail.items() if v is not None}
    step = PipelineTraceStep(
        message=message,
        phase=phase,
        detail=PipelineTraceDetail(**cleaned) if cleaned else None,
    )
    return {"type": "trace", "step": step.model_dump()}


def _maybe_trace(body: AskRequest, message: str, phase: str, **detail: Any) -> Iterator[dict[str, Any]]:
    if body.debug:
        yield _trace_event(body, message, phase, **detail)


def _truncate_debug_text(text: str, max_len: int = 6000) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}\n… [truncated]"


def _chunk_refs(chunks: list[dict]) -> list[PipelineChunkRef]:
    refs: list[PipelineChunkRef] = []
    for chunk in chunks:
        source_file = chunk.get("source", chunk.get("source_file", ""))
        chunk_id = chunk.get("chunk_id", "")
        if not source_file or not chunk_id:
            continue
        text = chunk.get("text") or ""
        refs.append(
            PipelineChunkRef(
                source_file=source_file,
                chunk_id=chunk_id,
                distance=chunk.get("distance"),
                domain_id=chunk.get("domain_id"),
                source_id=chunk.get("source_id"),
                text_preview=text[:280] + ("…" if len(text) > 280 else "") if text else None,
                verify_sql=chunk_verify_sql(source_file, chunk_id),
            )
        )
    return refs


def _result(response: AskResponse) -> dict[str, Any]:
    return {"type": "result", "data": response.model_dump()}


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def _usage_event(usage: dict[str, bool]) -> dict[str, Any]:
    return {"type": "usage", "rag": usage.get("rag", False), "mcp": usage.get("mcp", False)}


def _mark_rag(usage: dict[str, bool]) -> Iterator[dict[str, Any]]:
    if usage.get("rag"):
        return
    usage["rag"] = True
    yield _usage_event(usage)


def _mark_mcp(usage: dict[str, bool]) -> Iterator[dict[str, Any]]:
    changed = False
    if not usage.get("rag"):
        usage["rag"] = True
        changed = True
    if not usage.get("mcp"):
        usage["mcp"] = True
        changed = True
    if changed:
        yield _usage_event(usage)


def _response_from_meta(meta: dict[str, Any], **kwargs: Any) -> AskResponse:
    usage = meta.get("usage") or {}
    return AskResponse(
        used_rag=bool(usage.get("rag")),
        used_mcp=bool(usage.get("mcp")),
        **_session_fields(meta),
        **kwargs,
    )


def _scoped_search_kwargs(meta: dict[str, Any]) -> dict[str, Any]:
    routing = meta.get("routing") or {}
    domain_ids = routing.get("domain_ids")
    if domain_ids:
        if len(domain_ids) == 1:
            out: dict[str, Any] = {"domain_id": domain_ids[0]}
        else:
            out = {"domain_ids": domain_ids}
    else:
        domain_id = meta.get("domain_id")
        out = {"domain_id": domain_id} if domain_id else {}

    rag_source = meta.get("rag_source_id")
    if not rag_source and meta.get("execution_kind") == "rag":
        rag_source = meta.get("source_id")
    if rag_source:
        out["source_id"] = rag_source

    table_names = meta.get("table_names") or routing.get("table_names")
    file_names = meta.get("file_names") or routing.get("file_names")
    source_files = chunk_source_files_for_scope(
        domain_id=out.get("domain_id"),
        source_id=out.get("source_id"),
        table_names=table_names,
        file_names=file_names,
    )
    if source_files:
        out["source_files"] = source_files
    return out


def _scope_locked(meta: dict[str, Any]) -> bool:
    method = (meta.get("routing") or {}).get("method", "")
    return method in ("override", "override_multi")


def _vector_search_chunks(
    body: AskRequest,
    embedder,
    meta: dict[str, Any],
    domain_id: str | None,
) -> list[dict]:
    search_query = _retrieval_query(body, _meta_history(meta))
    scope_kwargs = _scoped_search_kwargs(meta)
    routing = meta.get("routing") or {}
    table_names = meta.get("table_names") or routing.get("table_names")
    file_names = meta.get("file_names") or routing.get("file_names")
    if _scope_locked(meta):
        chunks = search_chunks(
            search_query,
            embedder,
            top_k=body.top_k,
            **scope_kwargs,
        )
        return filter_chunks_to_rag_selection(
            chunks,
            source_id=scope_kwargs.get("source_id"),
            table_names=table_names,
            file_names=file_names,
        )

    chunks = search_chunks(
        search_query,
        embedder,
        top_k=body.top_k,
        **scope_kwargs,
    )
    chunks = filter_chunks_to_rag_selection(
        chunks,
        source_id=scope_kwargs.get("source_id"),
        table_names=table_names,
        file_names=file_names,
    )
    if not chunks and not _scope_locked(meta):
        chunks = search_chunks(search_query, embedder, top_k=body.top_k)
    return chunks


def _attachment_only_events(
    body: AskRequest,
    llm: tuple[str, str, str],
) -> Iterator[dict[str, Any]]:
    """Attachment-only path: read upload, extract relevant lines, answer via LLM."""
    llm_backend, llm_model, llm_base_url = llm
    user_question, attachment_raw = split_attached_documents(body.question)
    history = _conversation_history(body)
    chat_history = [
        {"role": t["role"], "content": t["content"]}
        for t in history
        if t.get("content") and ATTACHED_DOCS_MARKER not in t.get("content", "")
    ]

    yield _status("Reading attached document…")
    relevant = select_relevant_attachment_content(
        user_question or body.question,
        attachment_raw or "",
    )
    yield from _maybe_trace(
        body,
        "Attachment loaded",
        "input",
        attachment_chars=len(relevant),
        user_question=user_question,
    )

    yield _status("Generating answer from attachment…")
    prompt = build_attachment_answer_prompt(
        user_question,
        relevant,
        cite_sources=body.debug,
        conversation_history=chat_history or None,
    )
    yield from _maybe_trace(
        body,
        "Generating answer from attachment…",
        "llm",
        llm_prompt=_truncate_debug_text(prompt) if body.debug else None,
    )
    answer = generate_answer(
        prompt,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    if not body.debug:
        answer = strip_source_citations(answer)

    meta: dict[str, Any] = {
        "usage": {"rag": False, "mcp": False},
        "execution_kind": "attachment",
        "query_kind": "attachment",
        "conversation_history": history,
    }
    yield from _maybe_trace(
        body,
        "Answer generated from attachment",
        "output",
        execution_kind="attachment",
        query_kind="attachment",
    )
    yield _result(
        _response_from_meta(
            meta,
            answer=answer,
            question=body.question,
            domain_name=None,
            routing_method="attachment",
            routing_confidence=None,
            query_kind="attachment",
            sources=[],
        )
    )


def run_ask_events(body: AskRequest, embedder) -> Iterator[dict[str, Any]]:
    """Yield status events, then a single result event (or error)."""
    ensure_catalog_ready()
    llm_backend, llm_model, llm_base_url = resolve_llm_runtime(
        backend=body.backend,
        model=body.model,
        base_url=body.ollama_base_url,
    )

    selected_domains = normalize_domain_overrides(body.domain_override, body.domain_overrides)
    yield from _maybe_trace(
        body,
        "Question received",
        "input",
        question=body.question,
        top_k=body.top_k,
        domain_override=body.domain_override,
        domain_overrides=selected_domains or None,
    )

    if has_attached_documents(body.question):
        llm = (llm_backend, llm_model, llm_base_url)
        yield from _attachment_only_events(body, llm)
        return

    history = _conversation_history(body)
    session = prepare_session_context(
        body.question,
        history,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    history = session.effective_history
    if session.session_reset and session.session_summary:
        yield _status("Summarizing prior conversation — starting a new chat…")
    elif session.is_new_topic:
        yield _status("New topic detected — processing as a fresh question…")
    elif session.is_follow_up:
        yield _status(f"Using {session.prior_turn_count} prior turn(s) for follow-up context…")

    routing_question = (
        contextual_question_with_history(
            body.question,
            [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")],
        )
        if history
        else body.question
    )

    yield _status("Routing question to the best domain and dataset…")
    plan = resolve_query_plan(
        routing_question,
        embedder,
        domain_override=body.domain_override,
        domain_overrides=body.domain_overrides,
    )
    plan = coerce_to_sql_plan(
        plan,
        routing_question,
        embedder,
        allowed_domain_ids=selected_domains or None,
    )
    routing = plan.routing
    method = routing.get("method", "")

    if method == "override_multi" and plan.domain_name:
        yield _status(f"Using selected domains: {plan.domain_name}.")
        routing_msg = f"Using selected domains: {plan.domain_name}."
    elif method == "override" and plan.domain_name:
        yield _status(f"Using {plan.domain_name} domain (your selection).")
        routing_msg = f"Using {plan.domain_name} domain (your selection)."
    elif plan.domain_name:
        yield _status(f"Matched {plan.domain_name} domain.")
        routing_msg = f"Matched {plan.domain_name} domain."
    else:
        yield _status("No single domain match — searching all domains.")
        routing_msg = "No single domain match — searching all domains."

    yield from _maybe_trace(
        body,
        routing_msg,
        "routing",
        domain_id=plan.domain_id,
        domain_name=plan.domain_name,
        routing_method=routing.get("method"),
        routing_confidence=routing.get("confidence"),
        execution_kind=plan.execution_kind,
        source_id=plan.source_id,
        source_name=plan.source_name,
    )

    for note in plan.notes:
        yield _status(note)
        yield from _maybe_trace(body, note, "routing")

    if plan.source_name and plan.execution_kind in ("sql", "hybrid"):
        dataset_msg = f"Selected dataset «{plan.source_name}» ({plan.execution_kind.upper()} path)."
        yield _status(dataset_msg)
        yield from _maybe_trace(
            body,
            dataset_msg,
            "sql",
            source_id=plan.source_id,
            source_name=plan.source_name,
            domain_id=plan.domain_id,
            domain_name=plan.domain_name,
            execution_kind=plan.execution_kind,
        )
    elif plan.source_name and plan.execution_kind == "rag":
        dataset_msg = f"Narrowed search to dataset «{plan.source_name}»."
        yield _status(dataset_msg)
        yield from _maybe_trace(
            body,
            dataset_msg,
            "routing",
            source_id=plan.source_id,
            source_name=plan.source_name,
            domain_id=plan.domain_id,
            domain_name=plan.domain_name,
            execution_kind=plan.execution_kind,
            routing_method=routing.get("dataset_method"),
        )

    meta: dict[str, Any] = {
        "routing": routing,
        "domain_id": plan.domain_id,
        "domain_name": plan.domain_name,
        "execution_kind": plan.execution_kind,
        "query_kind": _legacy_query_kind(plan.execution_kind),
        "source_id": plan.source_id,
        "source_name": plan.source_name,
        "rag_source_id": plan.rag_source_id,
        "rag_source_name": plan.rag_source_name,
        "table_names": plan.table_names,
        "file_names": plan.file_names,
        "column_hints": plan.column_hints,
        "usage": {"rag": False, "mcp": False},
        "conversation_history": history,
        "session_reset": session.session_reset,
        "session_summary": session.session_summary,
        "new_topic": session.is_new_topic,
        "is_follow_up": session.is_follow_up,
    }

    llm = (llm_backend, llm_model, llm_base_url)

    if plan.execution_kind in ("sql", "hybrid"):
        yield from _structured_events(body, embedder, meta, llm)
        return

    yield from _rag_events(body, embedder, meta, llm)


def _mcp_enrichment_events(
    body: AskRequest,
    meta: dict[str, Any],
    llm: tuple[str, str, str],
    *,
    execution_kind: str,
) -> Iterator[dict[str, Any]]:
    """Plan and run domain MCP tools/resources/prompts; yields trace + final enrichment."""
    domain_id = meta.get("domain_id")
    if not domain_id:
        yield {"type": "_mcp_enrichment", "enrichment": None}
        return

    llm_backend, llm_model, llm_base_url = llm
    routing = meta.get("routing") or {}
    domain_slug = resolve_domain_slug(domain_id, routing)
    usage = meta.setdefault("usage", {"rag": False, "mcp": False})

    if not has_domain_mcp_bindings(domain_id):
        yield {"type": "_mcp_enrichment", "enrichment": None}
        return

    yield _status("Reviewing domain MCP tools, resources, and prompts…")
    plan = plan_mcp_enrichment(
        body.question,
        domain_id=domain_id,
        domain_slug=domain_slug,
        execution_kind=execution_kind,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    yield from _maybe_trace(
        body,
        f"MCP plan: {plan.get('reasoning', 'enrichment')}",
        "mcp",
        domain_id=domain_id,
        domain_name=meta.get("domain_name"),
        mcp_plan=plan,
    )

    yield _status("Loading MCP domain context…")
    enrichment = execute_mcp_enrichment(
        plan,
        question=body.question,
        domain_id=domain_id,
        domain_slug=domain_slug,
        top_k=body.top_k,
        execution_kind=execution_kind,
    )
    meta["mcp_enrichment"] = enrichment

    if enrichment.trace:
        yield from _mark_mcp(usage)
    for step in enrichment.trace:
        kind = step.get("kind")
        if kind == "tool":
            yield from _maybe_trace(
                body,
                f"MCP tool call: {step.get('tool')}",
                "mcp",
                mcp_url=step.get("mcp_url"),
                mcp_tool=step.get("tool"),
                mcp_arguments=step.get("arguments"),
                domain_id=domain_id,
                domain_name=meta.get("domain_name"),
            )
        elif kind == "resource":
            yield from _maybe_trace(
                body,
                f"MCP resource read: {step.get('uri')}",
                "mcp",
                mcp_resource=step.get("uri"),
                domain_id=domain_id,
                domain_name=meta.get("domain_name"),
            )
        elif kind == "prompt":
            yield from _maybe_trace(
                body,
                f"MCP prompt: {step.get('prompt') or step.get('mcp_prompt')}",
                "mcp",
                mcp_url=step.get("mcp_url"),
                domain_id=domain_id,
                domain_name=meta.get("domain_name"),
            )

    yield {"type": "_mcp_enrichment", "enrichment": enrichment}


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
        _retrieval_query(body, _meta_history(meta)),
        embedder,
        domain_override=body.domain_override,
        routing=routing,
        domain_id=meta.get("domain_id"),
        source_id=meta.get("source_id"),
        table_names=meta.get("table_names"),
        force_structured=True,
    )
    if not plan:
        yield _status("Structured query not applicable — searching documents instead…")
        yield from _rag_events(body, embedder, meta, llm)
        return

    ctx = plan.schema_context
    table_count = len(ctx.tables)
    dataset_msg = f"Using dataset «{ctx.source_name}» ({table_count} cataloged tables)."
    yield _status(dataset_msg)
    yield from _maybe_trace(
        body,
        dataset_msg,
        "sql",
        source_id=plan.source_id,
        source_name=ctx.source_name,
        domain_id=meta.get("domain_id"),
        domain_name=domain_name,
    )

    yield _status("Searching ingested catalog and documents for context…")
    mcp_enrichment = None
    for event in _mcp_enrichment_events(
        body, meta, llm, execution_kind=execution_kind or "sql"
    ):
        if event["type"] == "_mcp_enrichment":
            mcp_enrichment = event["enrichment"]
        else:
            yield event
    mcp_supplement = format_mcp_context_supplement(mcp_enrichment)

    rag_chunks: list[dict] = []
    for event in _rag_search_events(body, embedder, meta):
        if event["type"] == "status":
            yield event
        elif event["type"] == "usage":
            yield event
        elif event["type"] == "_chunks":
            rag_chunks = prioritize_chunks(event["chunks"])
            break

    if rag_chunks:
        yield _status(
            f"Found {len(rag_chunks)} ingested chunk(s) — blending with catalog definition for SQL…"
        )
    else:
        yield _status("No ingested chunks — generating SQL from catalog definition and schema…")

    history = _meta_history(meta)
    sql_history = history if meta.get("is_follow_up") else []
    prior = sql_history and len(sql_history) >= 2
    if prior:
        yield _status("Interpreting follow-up in context of the prior answer…")

    try:
        plan.sql, columns, rows, sql_notes = generate_and_execute_readonly_sql(
            body.question,
            plan.source_id,
            ctx,
            model=llm_model,
            backend=llm_backend,
            base_url=llm_base_url,
            rag_chunks=rag_chunks,
            mcp_supplement=mcp_supplement,
            conversation_history=sql_history,
        )
        yield _status("Running read-only query on the database…")
        yield from _maybe_trace(
            body,
            "SQL generated — executing read-only query",
            "sql",
            sql=plan.sql,
            source_id=plan.source_id,
            source_name=ctx.source_name,
            domain_id=meta.get("domain_id"),
            domain_name=domain_name,
        )
    except Exception as exc:
        if execution_kind == "sql":
            yield _result(
                _response_from_meta(
                    meta,
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

    columns, rows, _time_ctx = format_query_results_with_time_context(
        body.question,
        columns,
        rows,
        enrichment=mcp_enrichment,
    )

    row_count = len(rows)
    rows_msg = f"Retrieved {row_count} row{'s' if row_count != 1 else ''} — summarizing answer…"
    yield _status(rows_msg)
    yield from _maybe_trace(
        body,
        rows_msg,
        "sql",
        sql=plan.sql,
        source_id=plan.source_id,
        source_name=ctx.source_name,
        domain_id=meta.get("domain_id"),
        domain_name=domain_name,
        columns=columns,
        row_count=row_count,
    )

    summary_prompt = build_sql_summary_prompt(
        question=body.question,
        columns=columns,
        rows=rows,
        conversation_history=sql_history,
        table_rules=ctx.table_business_rules_block(),
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
        mcp_extra = format_mcp_context_supplement(mcp_enrichment)
        if rag_chunks:
            yield _status("Blending database results with retrieved document context…")
            doc_context, _ = build_domain_rag_prompt(
                f"{body.question}\n\nSupplement with document context if helpful.",
                rag_chunks,
                domain_name=domain_name,
                cite_sources=body.debug,
                conversation_history=[
                    {"role": t["role"], "content": t["content"]}
                    for t in _meta_history(meta)
                    if t.get("content")
                ],
            )
            blend_prompt = merge_generation_supplements(
                summary_prompt,
                mcp_extra,
                f"Additional retrieved context:\n{doc_context}",
            )
            answer = generate_answer(
                blend_prompt,
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
                for c in rag_chunks
            )
        else:
            yield _status("Also searching ingested documents…")
            for event in _rag_search_events(body, embedder, meta):
                if event["type"] == "status":
                    yield event
                elif event["type"] == "usage":
                    yield event
                elif event["type"] == "_chunks":
                    chunks = event["chunks"]
                    if chunks:
                        doc_context, _ = build_domain_rag_prompt(
                            f"{body.question}\n\nSupplement with document context if helpful.",
                            chunks,
                            domain_name=domain_name,
                            cite_sources=body.debug,
                            conversation_history=[
                    {"role": t["role"], "content": t["content"]}
                    for t in _meta_history(meta)
                    if t.get("content")
                ],
                        )
                        yield _status("Blending database results with document context…")
                        blend_prompt = merge_generation_supplements(
                            summary_prompt,
                            mcp_extra,
                            f"Additional document context:\n{doc_context}",
                        )
                        answer = generate_answer(
                            blend_prompt,
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

    yield from _maybe_trace(
        body,
        "Answer generated and displayed above",
        "output",
        execution_kind=execution_kind,
        query_kind="structured" if execution_kind == "sql" else "hybrid",
        domain_id=meta.get("domain_id"),
        domain_name=domain_name,
        sql=plan.sql if execution_kind in ("sql", "hybrid") else None,
        row_count=row_count,
    )

    yield _result(
        _response_from_meta(
            meta,
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
    """Search documents via MCP when the server is reachable, else local vector search."""
    usage = meta.setdefault("usage", {"rag": False, "mcp": False})
    routing = meta.get("routing") or {}
    domain_ids = routing.get("domain_ids")
    scope_kwargs = _scoped_search_kwargs(meta)
    domain_id = meta.get("domain_id")
    domain_slug = routing.get("domain_slug")
    chunks: list[dict] = []
    retrieval = "vector"
    mcp_meta: dict[str, Any] | None = None
    search_query = _retrieval_query(body, _meta_history(meta))

    domain_chunks, mcp_meta = retrieve_chunks_for_scope(
        search_query,
        domain_id=domain_id,
        domain_ids=domain_ids,
        domain_slug=domain_slug,
        top_k=body.top_k,
    )
    if domain_chunks:
        yield from _mark_mcp(usage)
        yield _status("Searching documents via domain MCP bindings…")
        url = mcp_meta.get("mcp_url") if mcp_meta else ""
        tool = mcp_meta.get("mcp_tool", "search_documents") if mcp_meta else "search_documents"
        mcp_args: dict[str, Any] = {"query": search_query, "top_k": body.top_k}
        if domain_ids and len(domain_ids) == 1 and domain_slug:
            mcp_args["domain"] = domain_slug
        yield from _maybe_trace(
            body,
            f"MCP tool call: {tool}",
            "mcp",
            retrieval="mcp",
            mcp_url=url,
            mcp_tool=tool,
            mcp_arguments=mcp_args,
            retrieval_query=search_query,
            top_k=body.top_k,
            domain_id=domain_id,
            domain_name=meta.get("domain_name"),
        )
        chunks = domain_chunks
        retrieval = "mcp"
        yield from _maybe_trace(
            body,
            f"MCP tool returned {len(chunks)} chunk(s)",
            "mcp",
            retrieval="mcp",
            mcp_url=url,
            mcp_tool=tool,
            mcp_arguments=mcp_args,
            retrieval_query=search_query,
            top_k=body.top_k,
            domain_id=domain_id,
            domain_name=meta.get("domain_name"),
            chunks=_chunk_refs(chunks),
        )

    if not chunks:
        search_msg = f"Searching ingested documents (top {body.top_k} chunks)…"
        if len(domain_ids or []) > 1:
            search_msg = f"Searching selected domains (top {body.top_k} chunks)…"
        yield _status(search_msg)
        yield from _maybe_trace(
            body,
            search_msg,
            "rag",
            retrieval="vector",
            retrieval_query=search_query,
            top_k=body.top_k,
            domain_id=domain_id,
            domain_name=meta.get("domain_name"),
            source_id=scope_kwargs.get("source_id"),
            source_name=meta.get("rag_source_name") or meta.get("source_name"),
        )
        domain_id_before = meta.get("domain_id")
        if retrieval == "mcp":
            yield _status("No MCP results — searching local index…")
        chunks = search_chunks(
            search_query,
            embedder,
            top_k=body.top_k,
            **scope_kwargs,
        )
        if not chunks and scope_kwargs.get("source_id"):
            yield _status("No chunks in selected dataset — searching full domain…")
            domain_only = {
                k: v
                for k, v in scope_kwargs.items()
                if k not in ("source_id", "source_files")
            }
            chunks = search_chunks(
                search_query,
                embedder,
                top_k=body.top_k,
                **domain_only,
            )
        if not chunks and scope_kwargs.get("source_files"):
            yield _status("No chunks in narrowed tables/files — searching full dataset…")
            widened = {
                k: v for k, v in scope_kwargs.items() if k != "source_files"
            }
            chunks = search_chunks(
                search_query,
                embedder,
                top_k=body.top_k,
                **widened,
            )
        if not chunks and not _scope_locked(meta):
            if domain_id_before:
                yield _status("No chunks in this domain — searching other domains…")
            chunks = _vector_search_chunks(body, embedder, meta, domain_id_before)
        elif not chunks and _scope_locked(meta):
            yield _status("No matching documents in selected domains.")
        if chunks and meta.get("domain_id") != domain_id_before:
            domain_name = meta.get("domain_name")
            if domain_name:
                yield _status(f"Found relevant documents in {domain_name} domain.")
        yield from _mark_rag(usage)
        retrieval = "vector"

    if chunks:
        routing = meta.get("routing") or {}
        chunks = filter_chunks_to_rag_selection(
            chunks,
            source_id=scope_kwargs.get("source_id"),
            table_names=meta.get("table_names") or routing.get("table_names"),
            file_names=meta.get("file_names") or routing.get("file_names"),
        )

    if chunks:
        found_msg = f"Found {len(chunks)} relevant chunk(s)."
        yield _status(found_msg)
        yield from _maybe_trace(
            body,
            found_msg,
            "rag" if retrieval == "vector" else "mcp",
            retrieval=retrieval,
            top_k=body.top_k,
            domain_id=meta.get("domain_id"),
            domain_name=meta.get("domain_name"),
            chunks=_chunk_refs(chunks),
        )
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
    mcp_enrichment = None
    for event in _mcp_enrichment_events(
        body, meta, llm, execution_kind=meta.get("execution_kind") or "rag"
    ):
        if event["type"] == "_mcp_enrichment":
            mcp_enrichment = event["enrichment"]
        else:
            yield event

    for event in _rag_search_events(body, embedder, meta):
        if event["type"] == "status":
            yield event
        elif event["type"] == "usage":
            yield event
        elif event["type"] == "_chunks":
            chunks = event["chunks"]

    fallback = structured_fallback_available(
        body.question,
        embedder,
        allowed_domain_ids=routing.get("domain_ids") if _scope_locked(meta) else None,
    )
    if fallback and not _scope_locked(meta) and (
        not chunks or meta.get("execution_kind") == "rag"
    ):
        if chunks:
            yield _status("Running database query for your data request…")
        else:
            for note in fallback.notes:
                yield _status(note)
        meta["domain_id"] = fallback.domain_id
        meta["domain_name"] = fallback.domain_name
        meta["execution_kind"] = "sql"
        meta["query_kind"] = "structured"
        meta["routing"] = fallback.routing
        yield from _structured_events(body, embedder, meta, llm)
        return

    if not chunks:
        from catalog_db import list_sources

        structured = (
            list_sources(domain_id=meta.get("domain_id"), source_type="structured", enabled_only=True)
            if meta.get("domain_id")
            else []
        )
        if structured:
            yield _status("No catalog embeddings found for this domain yet.")
            yield _result(
                _response_from_meta(
                    meta,
                    answer=(
                        "I could not find embedded catalog metadata for this question. "
                        "Ask for the data you need (for example, give me or show me …) to run a database query, "
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
            _response_from_meta(
                meta,
                answer="I do not know based on the provided documents.",
                domain_name=domain_name,
                routing_method=routing.get("method"),
                routing_confidence=routing.get("confidence"),
                query_kind=meta.get("query_kind"),
                sources=[],
            )
        )
        return

    gen_msg = "Generating answer from document context…"
    yield _status(gen_msg)
    domain_name = meta.get("domain_name") or domain_name
    history = _meta_history(meta)
    chat_history = [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")]

    mcp_extra = format_mcp_context_supplement(mcp_enrichment)
    table_rules = load_table_business_rules_for_domain(meta.get("domain_id"))
    _, prompt = build_domain_rag_prompt(
        body.question,
        chunks,
        domain_name=domain_name,
        cite_sources=body.debug,
        conversation_history=chat_history,
        catalog_supplement=table_rules,
    )
    if mcp_extra:
        prompt = merge_generation_supplements(mcp_extra, prompt)
    yield from _maybe_trace(
        body,
        gen_msg,
        "llm",
        domain_id=meta.get("domain_id"),
        domain_name=domain_name,
        retrieval_query=_retrieval_query(body, _meta_history(meta)),
        llm_prompt=_truncate_debug_text(prompt) if body.debug else None,
        chunks=_chunk_refs(chunks),
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

    yield from _maybe_trace(
        body,
        "Answer generated and displayed above",
        "output",
        execution_kind=meta.get("execution_kind"),
        query_kind=meta.get("query_kind"),
        domain_id=meta.get("domain_id"),
        domain_name=domain_name,
        chunks=_chunk_refs(chunks),
    )

    yield _result(
        _response_from_meta(
            meta,
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
