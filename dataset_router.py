"""Auto-select dataset within a domain using catalog metadata and RAG signals."""

from __future__ import annotations

import re
from dataset_connectors.registry import CONTENT_CONNECTORS

from catalog_db import get_rag_profile, list_column_metadata, list_sources, list_table_metadata
from catalog_definition import load_definition_for_prompt
from query_fuzzy import (
    build_vocabulary,
    correct_query_spelling,
    fuzzy_token_matches,
    fuzzy_token_overlap,
)
from routing_cache import get_cached_routing_context


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _cosine_sim(a, b) -> float:
    try:
        import numpy as np

        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    except Exception:
        return 0.0


def build_dataset_routing_text(source: dict, *, include_definition: bool = True) -> str:
    """Text for routing: name, description, definition, tables, columns, RAG instructions."""
    cached_text = source.get("routing_text")
    if cached_text:
        # routing_cache already includes definitions, tables, columns, and RAG profile.
        return cached_text

    parts = [
        source.get("name") or "",
        source.get("description") or "",
        source.get("slug") or "",
    ]

    if include_definition:
        try:
            definition = load_definition_for_prompt(source)
            if definition and definition != "(none)":
                parts.append(definition)
        except Exception:
            pass

        profile = get_rag_profile(source["id"])
        if profile:
            if profile.get("instructions"):
                parts.append(profile["instructions"])
            if profile.get("metadata_text"):
                parts.append(profile["metadata_text"])

        for table in list_table_metadata(source["id"]):
            if not table.get("enabled", True):
                continue
            role = table.get("table_role") or "fact"
            if role == "excluded":
                continue
            parts.append(table.get("table_name") or "")
            if table.get("definition"):
                parts.append(table["definition"])
            for col in list_column_metadata(table["id"]):
                parts.append(col.get("column_name") or "")
                parts.extend(col.get("labels") or [])
                if col.get("description"):
                    parts.append(col["description"])

    return "\n".join(p.strip() for p in parts if p and str(p).strip())


def _source_from_cache(domain_id: str, source_id: str) -> dict | None:
    for domain in get_cached_routing_context():
        if domain["id"] != domain_id:
            continue
        for source in domain.get("sources") or []:
            if source["id"] == source_id:
                return source
    return None


def score_dataset_keyword_fit(question: str, source: dict) -> float:
    routing_question, _ = correct_query_spelling(question, build_vocabulary())
    q_lower = routing_question.lower()
    q_tokens = _tokenize(routing_question)
    q_tokens.update(_tokenize(question))
    score = 0.0
    vocab = build_vocabulary()

    name = (source.get("name") or "").lower()
    slug = (source.get("slug") or "").lower()
    name_tokens = _tokenize(source.get("name") or "")
    slug_tokens = _tokenize(source.get("slug") or "")
    for tok in q_tokens:
        if tok in name or tok in slug:
            score += 2.0
        elif fuzzy_token_matches(tok, name_tokens | slug_tokens, vocab):
            score += 1.5

    routing_text = source.get("routing_text") or build_dataset_routing_text(source, include_definition=False)
    r_tokens = _tokenize(routing_text)
    overlap = fuzzy_token_overlap(q_tokens, r_tokens, vocab)
    score += overlap * 0.75

    for table_name in source.get("table_names") or []:
        tname = table_name.lower()
        if tname in q_lower or tname.replace("_", " ") in q_lower:
            score += 4.0
        for part in tname.split("_"):
            if len(part) > 2 and part in q_tokens:
                score += 1.5
            elif len(part) > 2 and fuzzy_token_matches(part, q_tokens, vocab):
                score += 1.0

    full_text = build_dataset_routing_text(source)
    full_lower = full_text.lower()
    for tok in q_tokens:
        if tok in full_lower and tok not in name:
            score += 0.25

    return score


def score_dataset_embedding_fit(
    question: str,
    source: dict,
    embedder,
    *,
    query_vector=None,
) -> float:
    if embedder is None:
        return 0.0
    text = build_dataset_routing_text(source)
    if not text.strip():
        return 0.0
    try:
        routing_question, _ = correct_query_spelling(question, build_vocabulary())
        if query_vector is None:
            query_vector = embedder.encode([routing_question])[0]
        doc_vec = embedder.encode([text[:12_000]])[0]
        return max(0.0, _cosine_sim(query_vector, doc_vec))
    except Exception:
        return 0.0


def score_dataset_chunk_fit(chunks: list[dict], source_id: str) -> float:
    """Higher when ingested chunks for this source match well (lower vector distance)."""
    dists = [
        float(c.get("distance", float("inf")))
        for c in chunks
        if c.get("source_id") == source_id
    ]
    if not dists:
        return 0.0
    best = min(dists)
    return max(0.0, 1.0 - best)


def pick_dataset_in_domain(
    question: str,
    domain_id: str,
    embedder=None,
    *,
    query_vector=None,
    source_type: str | None = None,
    connector: str | None = None,
    connectors: list[str] | None = None,
    chunks: list[dict] | None = None,
) -> tuple[dict | None, float, str]:
    """
    Pick the best dataset in a domain.
    Returns (source, confidence 0–1, method label).
    """
    candidates = list_sources(domain_id=domain_id, enabled_only=True)
    if source_type:
        candidates = [s for s in candidates if s.get("source_type") == source_type]
    if connector:
        candidates = [s for s in candidates if s.get("connector") == connector]
    if connectors:
        allowed = set(connectors)
        candidates = [s for s in candidates if s.get("connector") in allowed]
    if not candidates:
        return None, 0.0, "none"
    if len(candidates) == 1:
        return candidates[0], 1.0, "single_dataset"

    enriched: list[dict] = []
    for source in candidates:
        cached = _source_from_cache(domain_id, source["id"])
        merged = {**source}
        if cached:
            merged["routing_text"] = cached.get("routing_text")
            merged["table_names"] = cached.get("table_names") or []
        enriched.append(merged)

    scored: list[tuple[float, dict, float, float, float]] = []
    emb_scores: list[float] = [0.0] * len(enriched)
    if embedder is not None:
        texts = [build_dataset_routing_text(source)[:12_000] for source in enriched]
        non_empty = [(i, text) for i, text in enumerate(texts) if text.strip()]
        if non_empty:
            try:
                routing_question, _ = correct_query_spelling(question, build_vocabulary())
                if query_vector is None:
                    query_vector = embedder.encode([routing_question])[0]
                doc_vecs = embedder.encode([text for _, text in non_empty])
                for (idx, _), doc_vec in zip(non_empty, doc_vecs):
                    emb_scores[idx] = max(0.0, _cosine_sim(query_vector, doc_vec))
            except Exception:
                pass

    for i, source in enumerate(enriched):
        kw = score_dataset_keyword_fit(question, source)
        emb = emb_scores[i]
        chunk = score_dataset_chunk_fit(chunks or [], source["id"])
        total = kw + emb * 4.0 + chunk * 6.0
        scored.append((total, source, kw, emb, chunk))

    scored.sort(key=lambda row: row[0], reverse=True)
    best_total, best_source, kw, emb, chunk = scored[0]
    second_total = scored[1][0] if len(scored) > 1 else 0.0

    if best_total <= 0:
        return candidates[0], 0.0, "default_first"

    confidence = best_total / (best_total + second_total + 0.01)
    if chunk > 0 and chunk >= 0.3:
        method = "rag_metadata"
    elif emb >= 0.35:
        method = "embedding_metadata"
    elif kw >= 2:
        method = "keyword_metadata"
    else:
        method = "weak_metadata"

    return best_source, min(1.0, confidence), method


def pick_structured_dataset(
    question: str,
    domain_id: str,
    embedder=None,
    *,
    query_vector=None,
    chunks: list[dict] | None = None,
) -> dict | None:
    """Best postgres structured dataset in a domain."""
    source, confidence, _method = pick_dataset_in_domain(
        question,
        domain_id,
        embedder,
        query_vector=query_vector,
        source_type="structured",
        connector="postgres",
        chunks=chunks,
    )
    return source


def pick_rag_dataset(
    question: str,
    domain_id: str,
    embedder,
    *,
    query_vector=None,
    top_k: int = 3,
    allowed_domain_ids: list[str] | None = None,
) -> tuple[dict | None, float, str, list[dict]]:
    """
    Rank datasets in a domain using catalog metadata only (no content-chunk search).
    Returns (source, confidence, method, empty chunk list).
    """
    del top_k, allowed_domain_ids  # kept for API compatibility

    source, confidence, method = pick_dataset_in_domain(
        question,
        domain_id,
        embedder,
        query_vector=query_vector,
        chunks=None,
    )
    return source, confidence, method, []


def pick_file_dataset(question: str, domain_id: str, embedder=None, *, query_vector=None) -> dict | None:
    """Best content-backed unstructured dataset in a domain."""
    source, _confidence, _method = pick_dataset_in_domain(
        question,
        domain_id,
        embedder,
        query_vector=query_vector,
        connectors=list(CONTENT_CONNECTORS),
    )
    return source
