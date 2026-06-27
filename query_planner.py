"""
Multi-domain query planning: pick domain, dataset, and execution path (SQL / RAG / hybrid).

Resolves mismatches such as a Sales-titled question whose postgres tables live under
Finance Catalog, or document chunks that score better in a different domain than the
keyword router chose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from conversation_context import (
    has_attached_documents,
)
from catalog_db import get_domain
from catalog_service import normalize_domain_overrides
from code_orchestrator import ExecutionKind, classify_execution_kind
from dataset_router import pick_rag_dataset
from domain_router import route_question
from query_fuzzy import correct_query_spelling, encode_search_queries
from scope_resolver import resolve_catalog_scope
from structured_orchestrator import (
    find_best_structured_domain,
    pick_structured_dataset,
    should_use_structured_sql,
)

ExecutionPath = ExecutionKind


@dataclass
class QueryPlan:
    """Resolved domain + source + execution strategy for one user question."""

    question: str
    domain_id: str | None
    domain_name: str | None
    domain_slug: str | None
    execution_kind: ExecutionPath
    routing: dict[str, Any]
    source_id: str | None = None
    source_name: str | None = None
    rag_source_id: str | None = None
    rag_source_name: str | None = None
    rag_domain_id: str | None = None
    rag_domain_name: str | None = None
    table_names: list[str] = field(default_factory=list)
    file_names: list[str] = field(default_factory=list)
    column_hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def find_best_rag_domain(
    question: str,
    embedder,
    *,
    top_k: int = 3,
    prefer_domain_id: str | None = None,
    allowed_domain_ids: list[str] | None = None,
    query_vector=None,
) -> tuple[dict | None, list[dict]]:
    """Deprecated: domain routing uses catalog metadata only. Returns (domain, [])."""
    del question, embedder, top_k, query_vector
    if prefer_domain_id:
        domain = get_domain(domain_id=prefer_domain_id)
        return domain, []
    if allowed_domain_ids and len(allowed_domain_ids) == 1:
        domain = get_domain(domain_id=allowed_domain_ids[0])
        return domain, []
    return None, []


def _apply_catalog_scope(
    question: str,
    *,
    domain_id: str | None,
    source_id: str | None,
    rag_source_id: str | None,
    execution_kind: ExecutionPath,
    embedder=None,
    routing: dict[str, Any],
    notes: list[str],
) -> tuple[list[str], list[str], list[str], dict[str, Any]]:
    scope = resolve_catalog_scope(
        question,
        domain_id=domain_id,
        source_id=source_id,
        rag_source_id=rag_source_id,
        execution_kind=execution_kind,
        embedder=embedder,
    )
    routing = {
        **routing,
        "scope_method": scope.method,
        "scope_confidence": round(scope.confidence, 3) if scope.confidence else None,
    }
    if scope.table_names:
        notes.append(f"Narrowed to table(s): {', '.join(scope.table_names)}.")
        routing["table_names"] = scope.table_names
    if scope.file_names:
        notes.append(f"Narrowed to file(s): {', '.join(scope.file_names)}.")
        routing["file_names"] = scope.file_names
    if scope.column_hints:
        routing["column_hints"] = scope.column_hints
    return scope.table_names, scope.file_names, scope.column_hints, routing


def _domain_row(domain_id: str | None) -> dict | None:
    if not domain_id:
        return None
    return get_domain(domain_id=domain_id)


def resolve_query_plan(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
    domain_overrides: list[str] | None = None,
) -> QueryPlan:
    """
    Auto-detect domain and execution path across all catalog domains.

    Priority for analytical / table-aware questions: structured SQL in the best-matching
    domain. Otherwise: RAG in the domain with the strongest chunk match, falling back to
    the keyword/embedding domain router.

    When domain_overrides is set, search is limited to those domains and cross-domain
    auto-routing is skipped.

    When the user attached files in Ask (``[Attached documents]`` block), routing skips
    catalog SQL — the answer should use the upload as context, not postgres tables.
    """
    if has_attached_documents(question):
        return QueryPlan(
            question=question,
            execution_kind="attachment",
            routing={"method": "attachment"},
            notes=["Attached file(s) — answering from upload only."],
        )

    _, spelling_fixes = correct_query_spelling(question)
    query_vector = (
        encode_search_queries(embedder, question)[0]
        if embedder is not None
        else None
    )
    selected_overrides = normalize_domain_overrides(domain_override, domain_overrides)
    scope_locked = bool(selected_overrides)

    routing = route_question(
        question,
        embedder,
        domain_override=domain_override,
        domain_overrides=domain_overrides,
    )
    allowed_domain_ids = routing.get("domain_ids")
    routed_domain_id = routing.get("domain_id")
    routed_domain = _domain_row(routed_domain_id)

    notes: list[str] = []
    if spelling_fixes:
        fixes = ", ".join(f"{a}→{b}" for a, b in spelling_fixes[:3])
        notes.append(f"Adjusted query spelling for search ({fixes}).")
    if scope_locked and routing.get("domain_name"):
        if len(selected_overrides) == 1:
            notes.append(f"Searching only in {routing['domain_name']} (your selection).")
        else:
            notes.append(
                f"Searching only in selected domains: {routing['domain_name']}."
            )

    structured_domain, structured_score, structured_dataset = find_best_structured_domain(
        question,
        embedder,
        prefer_domain_id=routed_domain_id,
        allowed_domain_ids=allowed_domain_ids if scope_locked else None,
    )

    domain_id = routed_domain_id
    domain_name = routing.get("domain_name")
    domain_slug = routing.get("domain_slug")
    execution_kind: ExecutionPath = "rag"
    source_id: str | None = None
    source_name: str | None = None
    rag_source_id: str | None = None
    rag_source_name: str | None = None
    rag_domain_id: str | None = routed_domain_id
    rag_domain_name: str | None = domain_name

    use_structured = (
        structured_domain is not None
        and structured_score > 0
        and should_use_structured_sql(question, structured_domain["id"])
    )

    if use_structured and not scope_locked:
        if structured_domain and structured_domain["id"] != routed_domain_id:
            routed_label = domain_name or "the keyword match"
            notes.append(
                f"Structured tables for this question are in {structured_domain['name']} "
                f"(routed from {routed_label})."
            )
        domain_id = structured_domain["id"]
        domain_name = structured_domain["name"]
        domain_slug = structured_domain.get("slug")
        routing = {
            **routing,
            "domain_id": domain_id,
            "domain_name": domain_name,
            "domain_slug": domain_slug,
            "method": f"{routing.get('method', 'none')}+structured_catalog",
            "structured_score": structured_score,
        }
    elif use_structured and scope_locked and structured_domain:
        domain_id = structured_domain["id"]
        domain_name = structured_domain["name"]
        domain_slug = structured_domain.get("slug")

    if use_structured:
        execution_kind = classify_execution_kind(
            question, domain_id=domain_id, routing=routing
        )
        if execution_kind == "rag":
            execution_kind = "sql"
        dataset = structured_dataset
        if not dataset and domain_id:
            dataset = pick_structured_dataset(
                question, domain_id, embedder, query_vector=query_vector
            )
        if dataset:
            source_id = dataset["id"]
            source_name = dataset["name"]
    else:
        execution_kind = classify_execution_kind(
            question, domain_id=domain_id, routing=routing
        )
        if execution_kind in ("sql", "hybrid") and domain_id:
            dataset = pick_structured_dataset(
                question, domain_id, embedder, query_vector=query_vector
            )
            if dataset:
                source_id = dataset["id"]
                source_name = dataset["name"]
            else:
                execution_kind = "rag"
        elif execution_kind == "python":
            notes.append("File-based analytics detected; using document/RAG path until Python curation is enabled.")
            execution_kind = "rag"

    if embedder is not None and domain_id and execution_kind in ("rag", "hybrid"):
        rag_dataset, rag_conf, rag_method, _rag_pick_chunks = pick_rag_dataset(
            question,
            domain_id,
            embedder,
            query_vector=query_vector,
            allowed_domain_ids=allowed_domain_ids if scope_locked else None,
        )
        if rag_dataset and (rag_conf >= 0.12 or rag_method in ("embedding_metadata", "keyword_metadata", "weak_metadata")):
            rag_source_id = rag_dataset["id"]
            rag_source_name = rag_dataset["name"]
            routing = {
                **routing,
                "dataset_method": rag_method,
                "dataset_confidence": round(rag_conf, 3),
            }
            if execution_kind == "rag":
                source_id = rag_source_id
                source_name = rag_source_name
            notes.append(
                f"Auto-selected dataset «{rag_source_name}» "
                f"(matched via {rag_method.replace('_', ' ')})."
            )
        elif execution_kind == "hybrid":
            sql_dataset = pick_structured_dataset(
                question,
                domain_id,
                embedder,
                query_vector=query_vector,
            )
            if sql_dataset:
                source_id = sql_dataset["id"]
                source_name = sql_dataset["name"]

    if not domain_id and structured_domain and use_structured:
        domain_id = structured_domain["id"]
        domain_name = structured_domain["name"]
        domain_slug = structured_domain.get("slug")

    table_names, file_names, column_hints, routing = _apply_catalog_scope(
        question,
        domain_id=domain_id,
        source_id=source_id,
        rag_source_id=rag_source_id,
        execution_kind=execution_kind,
        embedder=embedder,
        routing=routing,
        notes=notes,
    )

    return QueryPlan(
        question=question,
        domain_id=domain_id,
        domain_name=domain_name,
        domain_slug=domain_slug,
        execution_kind=execution_kind,
        routing=routing,
        source_id=source_id,
        source_name=source_name,
        rag_source_id=rag_source_id,
        rag_source_name=rag_source_name,
        rag_domain_id=rag_domain_id,
        rag_domain_name=rag_domain_name,
        table_names=table_names,
        file_names=file_names,
        column_hints=column_hints,
        notes=notes,
    )


def structured_fallback_available(
    question: str,
    embedder=None,
    *,
    allowed_domain_ids: list[str] | None = None,
) -> QueryPlan | None:
    """When RAG finds nothing, return a SQL plan if any domain has matching structured data."""
    structured_domain, _score, structured_dataset = find_best_structured_domain(
        question,
        embedder,
        allowed_domain_ids=allowed_domain_ids,
    )
    if not structured_domain or not should_use_structured_sql(question, structured_domain["id"]):
        return None
    dataset = structured_dataset or pick_structured_dataset(
        question, structured_domain["id"], embedder, query_vector=embedder.encode([question])[0] if embedder else None
    )
    if not dataset:
        return None
    scope = resolve_catalog_scope(
        question,
        domain_id=structured_domain["id"],
        source_id=dataset["id"],
        rag_source_id=None,
        execution_kind="sql",
        embedder=embedder,
    )
    return QueryPlan(
        question=question,
        domain_id=structured_domain["id"],
        domain_name=structured_domain["name"],
        domain_slug=structured_domain.get("slug"),
        execution_kind="sql",
        routing={
            "method": "structured_fallback",
            "domain_id": structured_domain["id"],
            "scope_method": scope.method,
        },
        source_id=dataset["id"],
        source_name=dataset["name"],
        table_names=scope.table_names,
        file_names=scope.file_names,
        column_hints=scope.column_hints,
        notes=["No matching documents — querying catalog database instead."],
    )
