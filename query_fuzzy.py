"""Fuzzy spelling normalization for RAG vector search and metadata routing."""

from __future__ import annotations

import re
from difflib import SequenceMatcher, get_close_matches
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
WORD_RE = re.compile(r"[a-zA-Z]+")

# Domain terms that may not appear in routing metadata but matter for HR/policy questions.
EXTRA_VOCAB: frozenset[str] = frozenset(
    {
        "discrimination",
        "discriminate",
        "harassment",
        "retaliation",
        "employment",
        "opportunity",
        "benefits",
        "benefit",
        "handbook",
        "policies",
        "policy",
        "employee",
        "employees",
        "payroll",
        "vacation",
        "leave",
        "termination",
        "onboarding",
        "compensation",
        "salary",
        "wages",
        "overtime",
        "disability",
        "accommodation",
        "grievance",
        "complaint",
        "compliance",
        "ethics",
        "conduct",
        "travel",
        "expense",
        "reimbursement",
        "invoice",
        "budget",
        "accounting",
        "revenue",
        "customer",
        "segment",
        "sales",
        "pricing",
        "contract",
        "non",
    }
)

# Profile supplement chunks are useful for routing but poor RAG answers.
SUPPLEMENT_SOURCE_MARKERS = ("_instructions", "_metadata")

_vocab_cache: set[str] | None = None


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or "") if len(t) > 2}


def clear_vocabulary_cache() -> None:
    global _vocab_cache
    _vocab_cache = None


def build_vocabulary() -> set[str]:
    """Tokens from catalog routing metadata plus common domain terms."""
    global _vocab_cache
    if _vocab_cache is not None:
        return _vocab_cache

    vocab: set[str] = set(EXTRA_VOCAB)
    try:
        from routing_cache import get_cached_routing_context

        for domain in get_cached_routing_context():
            vocab.update(tokenize(domain.get("name") or ""))
            vocab.update(tokenize(domain.get("description") or ""))
            vocab.update(tokenize(domain.get("slug") or ""))
            for source in domain.get("sources") or []:
                vocab.update(tokenize(source.get("name") or ""))
                vocab.update(tokenize(source.get("description") or ""))
                vocab.update(tokenize(source.get("slug") or ""))
                vocab.update(tokenize(source.get("routing_text") or ""))
                for table_name in source.get("table_names") or []:
                    vocab.update(tokenize(table_name.replace("_", " ")))
    except Exception:
        pass

    _vocab_cache = vocab
    return vocab


def fuzzy_correct_token(token: str, vocabulary: set[str] | None = None, *, cutoff: float = 0.84) -> str:
    """Return the closest vocabulary token when the input looks misspelled."""
    lower = token.lower()
    if len(lower) <= 3:
        return lower

    vocab = vocabulary or build_vocabulary()
    if lower in vocab:
        return lower

    matches = get_close_matches(lower, vocab, n=1, cutoff=cutoff)
    if matches:
        return matches[0]

    if len(lower) >= 6:
        matches = get_close_matches(lower, vocab, n=1, cutoff=0.78)
        if matches:
            return matches[0]

    return lower


def correct_query_spelling(
    question: str,
    vocabulary: set[str] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """Return question text with likely typos fixed, plus (original, fixed) pairs."""
    vocab = vocabulary or build_vocabulary()
    corrections: list[tuple[str, str]] = []
    parts: list[str] = []
    last_end = 0

    for match in WORD_RE.finditer(question):
        parts.append(question[last_end : match.start()])
        word = match.group(0)
        lower = word.lower()
        if len(lower) > 3:
            fixed = fuzzy_correct_token(lower, vocab)
            if fixed != lower:
                corrections.append((lower, fixed))
                if word.isupper():
                    word = fixed.upper()
                elif word[0].isupper():
                    word = fixed.capitalize()
                else:
                    word = fixed
        parts.append(word)
        last_end = match.end()

    parts.append(question[last_end:])
    return "".join(parts), corrections


def get_search_query_variants(question: str, vocabulary: set[str] | None = None) -> list[str]:
    """Unique query strings for retrieval (original first, then spelling-corrected)."""
    corrected, corrections = correct_query_spelling(question, vocabulary)
    variants = [question]
    if corrections and corrected not in variants:
        variants.append(corrected)
    return variants


def encode_search_queries(embedder, question: str, vocabulary: set[str] | None = None) -> list[Any]:
    """Encode one or two query variants for fuzzy vector search."""
    variants = get_search_query_variants(question, vocabulary)
    if len(variants) == 1:
        return [embedder.encode([variants[0]])[0]]
    return list(embedder.encode(variants))


def fuzzy_token_matches(token: str, candidates: set[str], vocabulary: set[str] | None = None) -> bool:
    """True when token matches a candidate exactly, after correction, or fuzzily."""
    lower = token.lower()
    if lower in candidates:
        return True

    corrected = fuzzy_correct_token(lower, vocabulary)
    if corrected in candidates:
        return True

    if len(lower) < 4:
        return False

    for candidate in candidates:
        if SequenceMatcher(None, lower, candidate).ratio() >= 0.84:
            return True
    return False


def fuzzy_token_overlap(question_tokens: set[str], text_tokens: set[str], vocabulary: set[str] | None = None) -> int:
    """Count question tokens that fuzzy-match text tokens."""
    return sum(1 for token in question_tokens if fuzzy_token_matches(token, text_tokens, vocabulary))


def _is_supplement_chunk(chunk: dict) -> bool:
    source = (chunk.get("source") or chunk.get("source_file") or "").lower()
    return any(marker in source for marker in SUPPLEMENT_SOURCE_MARKERS)


def merge_ranked_chunks(result_lists: list[list[dict]], top_k: int) -> list[dict]:
    """Merge vector hits from multiple query variants; keep best distance per chunk."""
    by_key: dict[tuple[str, str], dict] = {}
    for chunks in result_lists:
        for chunk in chunks:
            source = chunk.get("source", chunk.get("source_file", ""))
            chunk_id = chunk.get("chunk_id", "")
            key = (source, chunk_id)
            distance = float(chunk.get("distance", float("inf")))
            if _is_supplement_chunk(chunk):
                distance += 0.18
            prev = by_key.get(key)
            if prev is None or distance < float(prev.get("distance", float("inf"))):
                merged = dict(chunk)
                merged["distance"] = distance
                by_key[key] = merged

    ranked = sorted(by_key.values(), key=lambda c: float(c.get("distance", float("inf"))))
    return ranked[:top_k]
