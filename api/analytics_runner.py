"""Analytics dashboard pipeline — SQL-first with live preview widgets."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from api.analytics_builder import build_dashboard
from api.analytics_models import AnalyticsRequest, AnalyticsResponse
from api.answer_format import build_analytics_summary_prompt
from api.llm import generate_answer, resolve_llm_runtime
from catalog_service import ensure_catalog_ready
from query_planner import resolve_query_plan, structured_fallback_available
from structured_orchestrator import generate_and_execute_readonly_sql, plan_structured_query


def _status(message: str) -> dict[str, Any]:
    return {"type": "status", "message": message}


def _result(data: AnalyticsResponse) -> dict[str, Any]:
    return {"type": "result", "data": data.model_dump()}


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


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

    yield _status("Analyzing prompt across domains and data sources…")
    plan = resolve_query_plan(prompt, embedder, domain_override=body.domain_override)

    if plan.execution_kind not in ("sql", "hybrid") and not body.domain_override:
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
        yield _result(dash)
        return

    yield _status("Loading catalog schema…")
    sql_plan = plan_structured_query(
        prompt,
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
        yield _result(dash)
        return

    ctx = sql_plan.schema_context
    yield _status(f"Querying «{ctx.source_name}» ({len(ctx.tables)} tables)…")

    try:
        yield _status("Generating SQL from catalog…")
        sql, columns, rows, sql_notes = generate_and_execute_readonly_sql(
            prompt,
            sql_plan.source_id,
            ctx,
            model=llm_model,
            backend=llm_backend,
            base_url=llm_base_url,
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
        yield _result(dash)
        return

    yield _status(f"Building dashboard from {len(rows)} row(s)…")
    summary_prompt = build_analytics_summary_prompt(
        question=prompt,
        columns=columns,
        rows=rows,
        gap_notes=sql_notes,
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
    )
    yield _result(dash)


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
