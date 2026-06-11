"""
Multi-domain query planning: pick domain, dataset, and execution path (SQL / RAG / hybrid).

Resolves mismatches such as a Sales-titled question whose postgres tables live under
Finance Catalog, or document chunks that score better in a different domain than the
keyword router chose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from catalog_db import get_domain, list_domains
from code_orchestrator import ExecutionKind, classify_execution_kind
from domain_router import route_question
from db import search_chunks
from structured_orchestrator import (
    find_best_structured_domain,
    pick_structured_dataset,
    score_structured_domain_fit,
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
    rag_domain_id: str | None = None
    rag_domain_name: str | None = None
    notes: list[str] = field(default_factory=list)


def find_best_rag_domain(
    question: str,
    embedder,
    *,
    top_k: int = 3,
    prefer_domain_id: str | None = None,
    query_vector=None,
) -> tuple[dict | None, list[dict]]:
    """Domain whose ingested chunks best match the question (single vector search)."""
    if query_vector is None:
        query_vector = embedder.encode([question])[0]

    chunks = search_chunks(
        question,
        embedder,
        top_k=max(top_k * 3, 12),
        query_vector=query_vector,
    )
    if not chunks:
        return None, []

    best_by_domain: dict[str, dict] = {}
    for chunk in chunks:
        did = chunk.get("domain_id")
        if not did:
            continue
        dist = float(chunk.get("distance", float("inf")))
        if did == prefer_domain_id:
            dist -= 0.05
        prev = best_by_domain.get(did)
        if prev is None or dist < float(prev.get("_score", float("inf"))):
            best_by_domain[did] = {**chunk, "_score": dist}

    if not best_by_domain:
        domain_id = chunks[0].get("domain_id")
        if domain_id:
            domain = get_domain(domain_id=domain_id)
            if domain:
                return domain, chunks[:top_k]
        return None, chunks[:top_k]

    winner_id = min(best_by_domain, key=lambda did: best_by_domain[did]["_score"])
    domain = get_domain(domain_id=winner_id)
    if not domain:
        return None, []

    winner_chunks = [
        {k: v for k, v in c.items() if k != "_score"}
        for c in chunks
        if c.get("domain_id") == winner_id
    ][:top_k]
    return domain, winner_chunks


def _domain_row(domain_id: str | None) -> dict | None:
    if not domain_id:
        return None
    return get_domain(domain_id=domain_id)


def resolve_query_plan(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
) -> QueryPlan:
    """
    Auto-detect domain and execution path across all catalog domains.

    Priority for analytical / table-aware questions: structured SQL in the best-matching
    domain. Otherwise: RAG in the domain with the strongest chunk match, falling back to
    the keyword/embedding domain router.
    """
    query_vector = embedder.encode([question])[0] if embedder is not None else None

    routing = route_question(question, embedder, domain_override=domain_override)
    routed_domain_id = routing.get("domain_id")
    routed_domain = _domain_row(routed_domain_id)

    notes: list[str] = []
    structured_domain = find_best_structured_domain(
        question, embedder, prefer_domain_id=routed_domain_id
    )
    structured_score = (
        score_structured_domain_fit(question, structured_domain["id"], embedder)
        if structured_domain
        else 0
    )

    domain_id = routed_domain_id
    domain_name = routing.get("domain_name")
    domain_slug = routing.get("domain_slug")
    execution_kind: ExecutionPath = "rag"
    source_id: str | None = None
    source_name: str | None = None
    rag_domain_id: str | None = routed_domain_id
    rag_domain_name: str | None = domain_name

    use_structured = (
        structured_domain is not None
        and structured_score > 0
        and should_use_structured_sql(question, structured_domain["id"])
    )

    if use_structured and not domain_override:
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
    elif use_structured and domain_override and structured_domain:
        domain_id = structured_domain["id"]
        domain_name = structured_domain["name"]
        domain_slug = structured_domain.get("slug")

    if use_structured:
        execution_kind = classify_execution_kind(
            question, domain_id=domain_id, routing=routing
        )
        if execution_kind == "rag":
            execution_kind = "sql"
        dataset = pick_structured_dataset(question, domain_id, embedder) if domain_id else None
        if dataset:
            source_id = dataset["id"]
            source_name = dataset["name"]
    else:
        execution_kind = classify_execution_kind(
            question, domain_id=domain_id, routing=routing
        )
        if execution_kind in ("sql", "hybrid") and domain_id:
            dataset = pick_structured_dataset(question, domain_id, embedder)
            if dataset:
                source_id = dataset["id"]
                source_name = dataset["name"]
            else:
                execution_kind = "rag"
        elif execution_kind == "python":
            notes.append("File-based analytics detected; using document search until Python curation is enabled.")
            execution_kind = "rag"

        if embedder is not None and execution_kind in ("rag", "hybrid"):
            rag_domain, rag_chunks = find_best_rag_domain(
                question,
                embedder,
                prefer_domain_id=domain_id,
                query_vector=query_vector,
            )
            if rag_domain and rag_chunks:
                rag_domain_id = rag_domain["id"]
                rag_domain_name = rag_domain["name"]
                if rag_domain_id != domain_id and not domain_override:
                    notes.append(
                        f"Best document match is in {rag_domain_name} "
                        f"(keyword router chose {domain_name or 'all domains'})."
                    )
                    domain_id = rag_domain_id
                    domain_name = rag_domain_name
                    domain_slug = rag_domain.get("slug")
                    routing = {
                        **routing,
                        "domain_id": domain_id,
                        "domain_name": domain_name,
                        "domain_slug": domain_slug,
                        "method": f"{routing.get('method', 'none')}+rag_catalog",
                    }

    if not domain_id and structured_domain and use_structured:
        domain_id = structured_domain["id"]
        domain_name = structured_domain["name"]
        domain_slug = structured_domain.get("slug")

    return QueryPlan(
        question=question,
        domain_id=domain_id,
        domain_name=domain_name,
        domain_slug=domain_slug,
        execution_kind=execution_kind,
        routing=routing,
        source_id=source_id,
        source_name=source_name,
        rag_domain_id=rag_domain_id,
        rag_domain_name=rag_domain_name,
        notes=notes,
    )


def structured_fallback_available(question: str, embedder=None) -> QueryPlan | None:
    """When RAG finds nothing, return a SQL plan if any domain has matching structured data."""
    structured_domain = find_best_structured_domain(question, embedder)
    if not structured_domain or not should_use_structured_sql(question, structured_domain["id"]):
        return None
    dataset = pick_structured_dataset(question, structured_domain["id"], embedder)
    if not dataset:
        return None
    return QueryPlan(
        question=question,
        domain_id=structured_domain["id"],
        domain_name=structured_domain["name"],
        domain_slug=structured_domain.get("slug"),
        execution_kind="sql",
        routing={"method": "structured_fallback", "domain_id": structured_domain["id"]},
        source_id=dataset["id"],
        source_name=dataset["name"],
        notes=["No matching documents — querying catalog database instead."],
    )
