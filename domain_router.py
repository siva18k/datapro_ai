"""Route user questions to the best-matching business domain."""

from __future__ import annotations

import re
from typing import Any

from catalog_service import get_routing_context, normalize_domain_overrides, resolve_domains
from query_fuzzy import (
    build_vocabulary,
    correct_query_spelling,
    fuzzy_token_overlap,
)


def _domain_routing_text(domain: dict) -> str:
    """Keywords for routing: domain, sources, and cataloged table names."""
    parts = [
        domain["name"],
        domain.get("description") or "",
        " ".join(
            s["name"] + " " + (s.get("description") or "")
            for s in domain.get("sources") or []
        ),
    ]
    for source in domain.get("sources") or []:
        for table_name in source.get("table_names") or []:
            parts.append(table_name.replace("_", " "))
    return " ".join(parts)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def route_question(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
    domain_overrides: list[str] | None = None,
) -> dict[str, Any]:
    """Return domain_id, domain_slug, domain_name, confidence, method."""
    overrides = normalize_domain_overrides(domain_override, domain_overrides)
    if overrides:
        selected = resolve_domains(overrides)
        if selected:
            names = ", ".join(domain["name"] for domain in selected)
            slugs = [domain["slug"] for domain in selected]
            ids = [domain["id"] for domain in selected]
            primary = selected[0]
            method = "override" if len(selected) == 1 else "override_multi"
            return {
                "domain_id": primary["id"],
                "domain_slug": primary["slug"],
                "domain_name": names,
                "domain_ids": ids,
                "domain_slugs": slugs,
                "confidence": 1.0,
                "method": method,
            }

    domains = get_routing_context()
    if not domains:
        return {
            "domain_id": None,
            "domain_slug": None,
            "domain_name": None,
            "confidence": 0.0,
            "method": "none",
        }

    if len(domains) == 1:
        d = domains[0]
        return {
            "domain_id": d["id"],
            "domain_slug": d["slug"],
            "domain_name": d["name"],
            "confidence": 1.0,
            "method": "single_domain",
        }

    q_tokens = _tokenize(question)
    routing_question, _ = correct_query_spelling(question, build_vocabulary())
    q_tokens_expanded = _tokenize(routing_question) | q_tokens
    scores: list[tuple[float, dict]] = []

    q_vec = None
    d_vecs: list = []
    if embedder is not None:
        try:
            import numpy as np

            texts = [routing_question] + [
                domain["name"] + ". " + (domain.get("description") or "")
                for domain in domains
            ]
            encoded = embedder.encode(texts)
            q_vec = encoded[0]
            d_vecs = encoded[1:]
        except Exception:
            q_vec = None
            d_vecs = []

    vocab = build_vocabulary()
    for i, domain in enumerate(domains):
        text = _domain_routing_text(domain)
        d_tokens = _tokenize(text)
        overlap = fuzzy_token_overlap(q_tokens_expanded, d_tokens, vocab)
        keyword_score = overlap / max(len(q_tokens_expanded), 1)

        embed_score = 0.0
        if q_vec is not None and i < len(d_vecs):
            try:
                import numpy as np

                d_vec = d_vecs[i]
                sim = float(
                    np.dot(q_vec, d_vec)
                    / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec) + 1e-9)
                )
                embed_score = max(0.0, sim)
            except Exception:
                embed_score = 0.0

        # Explicit HR/finance/sales keyword boosts
        slug = domain["slug"]
        boost = 0.0
        if slug == "hr" and re.search(r"\b(hr|human resources|employee|policy|handbook|benefits|leave|travel)\b", question, re.I):
            boost = 0.35
        if slug == "finance" and re.search(
            r"\b(finance|budget|expense|accounting|invoice|payment|cost|segment|ledger|gl)\b",
            question,
            re.I,
        ):
            boost = 0.35
        if slug == "finance" and re.search(r"\bcustomer\b", question, re.I):
            boost = max(boost, 0.3)
        if slug == "finance" and re.search(r"\bsegment", question, re.I):
            boost = max(boost, 0.45)
        if slug == "sales" and re.search(r"\b(sales|deal|pricing|contract|revenue|quota)\b", question, re.I):
            boost = 0.35
        if slug == "sales" and re.search(r"\bcustomer\b", question, re.I):
            if not re.search(r"\b(segment|account|finance|invoice)\b", question, re.I):
                boost = max(boost, 0.35)

        score = keyword_score * 0.5 + embed_score * 0.35 + boost
        scores.append((score, domain))

    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best_domain = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0

    confidence = best_score
    if best_score - second_score < 0.08 and best_score < 0.25:
        return {
            "domain_id": None,
            "domain_slug": None,
            "domain_name": None,
            "confidence": best_score,
            "method": "low_confidence_fallback_all",
            "candidates": [(s, d["slug"]) for s, d in scores[:3]],
        }

    return {
        "domain_id": best_domain["id"],
        "domain_slug": best_domain["slug"],
        "domain_name": best_domain["name"],
        "confidence": confidence,
        "method": "hybrid",
        "candidates": [(s, d["slug"]) for s, d in scores[:3]],
    }
