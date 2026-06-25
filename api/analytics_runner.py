"""Analytics dashboard pipeline — SQL-first with live preview widgets."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from api.analytics_builder import build_dashboard
from api.analytics_models import AnalyticsRequest, AnalyticsResponse
from api.answer_format import build_analytics_summary_prompt
from api.llm import generate_answer, resolve_llm_runtime
from catalog_service import ensure_catalog_ready, normalize_domain_overrides
from conversation_context import contextual_question_with_history, truncate_history
from conversation_session import prepare_session_context
from hybrid_prompt import prioritize_chunks, retrieve_hybrid_chunks
from mcp_ask_planner import (
    execute_mcp_enrichment,
    format_mcp_context_supplement,
    plan_mcp_enrichment,
    resolve_domain_slug,
)
from temporal_context import format_query_results_with_time_context
from query_planner import resolve_query_plan, structured_fallback_available
from structured_orchestrator import generate_and_execute_readonly_sql, plan_structured_query


def _time_context_from_enrichment(enrichment) -> dict[str, Any] | None:
    from temporal_context import time_context_from_mcp_enrichment

    return time_context_from_mcp_enrichment(enrichment)


def _resolve_time_context(prompt: str, enrichment) -> dict[str, Any] | None:
    from temporal_context import fetch_time_context

    from_mcp = _time_context_from_enrichment(enrichment)
    if from_mcp:
        return from_mcp
    return fetch_time_context(prompt)


def _status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def _result(data: AnalyticsResponse) -> dict[str, Any]:
    return {"type": "result", "data": data.model_dump()}


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def _analytics_history(body: AnalyticsRequest) -> list[dict[str, Any]]:
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


def _attach_session(dash: AnalyticsResponse, session) -> AnalyticsResponse:
    return dash.model_copy(
        update={
            "session_reset": session.session_reset,
            "session_summary": session.session_summary,
            "new_topic": session.is_new_topic,
        }
    )


def run_analytics_events(body: AnalyticsRequest, embedder) -> Iterator[dict[str, Any]]:
    ensure_catalog_ready()
    llm_backend, llm_model, llm_base_url = resolve_llm_runtime(
        backend=body.backend,
        model=body.model,
        base_url=body.ollama_base_url,
    )
    prompt = body.prompt.strip()
    if not prompt:
        yield _error("Enter a question or dashboard requirements.")
        return

    raw_history = _analytics_history(body)
    session = prepare_session_context(
        prompt,
        raw_history,
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

    routing_prompt = (
        contextual_question_with_history(
            prompt,
            [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")],
        )
        if history
        else prompt
    )

    yield _status("Analyzing prompt across domains and data sources…")
    selected_domains = normalize_domain_overrides(body.domain_override, body.domain_overrides)
    scope_locked = bool(selected_domains)
    plan = resolve_query_plan(
        routing_prompt,
        embedder,
        domain_override=body.domain_override,
        domain_overrides=body.domain_overrides,
    )

    if plan.execution_kind not in ("sql", "hybrid") and not scope_locked:
        fallback = structured_fallback_available(prompt, embedder)
        if fallback:
            plan = fallback

    for note in plan.notes:
        yield _status(note)

    if plan.domain_name:
        yield _status(f"Using {plan.domain_name} domain.")
    elif plan.execution_kind in ("sql", "hybrid"):
        yield _status("Structured dataset found.")

    if plan.execution_kind not in ("sql", "hybrid") or not plan.domain_id:
        dash = build_dashboard(
            prompt=prompt,
            summary=(
                "This prompt looks like a document question. Analytics works best with "
                "**structured postgres datasets** — try metrics like *revenue by country*, "
                "*top customers*, or *employee count by department*."
            ),
            columns=None,
            rows=None,
            domain_name=plan.domain_name,
            routing_method=plan.routing.get("method"),
        )
        yield _result(_attach_session(dash, session))
        return

    yield _status("Loading catalog schema…")
    sql_plan = plan_structured_query(
        routing_prompt,
        embedder,
        domain_id=plan.domain_id,
        routing=plan.routing,
        force_structured=True,
    )
    if not sql_plan:
        dash = build_dashboard(
            prompt=prompt,
            summary="Could not find a structured dataset for this prompt.",
            columns=None,
            rows=None,
            domain_name=plan.domain_name,
            routing_method=plan.routing.get("method"),
        )
        yield _result(_attach_session(dash, session))
        return

    ctx = sql_plan.schema_context
    yield _status(f"Querying «{ctx.source_name}» ({len(ctx.tables)} tables)…")

    domain_slug = resolve_domain_slug(plan.domain_id, plan.routing)
    mcp_plan = plan_mcp_enrichment(
        prompt,
        domain_id=plan.domain_id,
        domain_slug=domain_slug,
        execution_kind=plan.execution_kind,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )
    mcp_enrichment = execute_mcp_enrichment(
        mcp_plan,
        question=prompt,
        domain_id=plan.domain_id,
        domain_slug=domain_slug,
        top_k=5,
    )
    mcp_supplement = format_mcp_context_supplement(mcp_enrichment)
    if mcp_enrichment.trace:
        yield _status("Loaded domain MCP context for SQL generation…")

    rag_chunks = prioritize_chunks(
        retrieve_hybrid_chunks(
            prompt,
            embedder,
            domain_id=plan.domain_id,
            source_id=sql_plan.source_id,
            top_k=5,
        )
    )
    if rag_chunks:
        yield _status(f"Found {len(rag_chunks)} ingested chunk(s) for SQL context…")
    else:
        yield _status("Generating SQL from catalog definition…")

    if history and len(history) >= 2 and session.is_follow_up:
        yield _status("Interpreting follow-up in context of the prior dashboard…")

    try:
        sql_history = history if session.is_follow_up else []
        sql, columns, rows, sql_notes = generate_and_execute_readonly_sql(
            prompt,
            sql_plan.source_id,
            ctx,
            model=llm_model,
            backend=llm_backend,
            base_url=llm_base_url,
            rag_chunks=rag_chunks,
            mcp_supplement=mcp_supplement,
            conversation_history=sql_history,
        )
        sql_plan.sql = sql
    except Exception as exc:
        dash = build_dashboard(
            prompt=prompt,
            summary="Could not retrieve data for this question. Check catalog tables or try a simpler prompt.",
            columns=None,
            rows=None,
            domain_name=plan.domain_name,
            routing_method=plan.routing.get("method"),
            sql=getattr(sql_plan, "sql", None) or None,
            notes=[f"Query failed: {exc}"],
        )
        yield _result(_attach_session(dash, session))
        return

    yield _status(f"Building dashboard from {len(rows)} row(s)…")
    time_context = _resolve_time_context(prompt, mcp_enrichment)
    columns, rows, time_context = format_query_results_with_time_context(
        prompt,
        columns,
        rows,
        time_context=time_context,
        enrichment=mcp_enrichment,
    )
    summary_prompt = build_analytics_summary_prompt(
        question=prompt,
        columns=columns,
        rows=rows,
        gap_notes=sql_notes,
        conversation_history=(
            [{"role": t["role"], "content": t["content"]} for t in history]
            if session.is_follow_up
            else None
        ),
        table_rules=ctx.table_business_rules_block(),
    )
    summary = generate_answer(
        summary_prompt,
        model=llm_model,
        backend=llm_backend,
        base_url=llm_base_url,
    )

    dash = build_dashboard(
        prompt=prompt,
        summary=summary,
        columns=columns,
        rows=rows,
        domain_name=plan.domain_name,
        routing_method=plan.routing.get("method"),
        sql=sql_plan.sql,
        notes=sql_notes,
        time_context=time_context,
    )
    yield _result(_attach_session(dash, session))


def collect_analytics_response(body: AnalyticsRequest, embedder) -> AnalyticsResponse:
    response: AnalyticsResponse | None = None
    for event in run_analytics_events(body, embedder):
        if event["type"] == "result":
            response = AnalyticsResponse(**event["data"])
        elif event["type"] == "error":
            raise RuntimeError(event["message"])
    if response is None:
        raise RuntimeError("Analytics pipeline produced no response")
    return response
