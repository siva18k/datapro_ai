"""Narrow catalog scope to tables, files, and columns after domain/dataset routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from catalog_db import get_source, list_column_metadata, list_source_file_rag, list_sources, list_table_metadata
from catalog_rag_service import CATALOG_SOURCE_PREFIX, LOOKUP_SOURCE_PREFIX
from catalog_service import list_source_files
from query_fuzzy import build_vocabulary, correct_query_spelling, fuzzy_token_matches, fuzzy_token_overlap
from structured_sql import is_structured_sql_connector

MAX_TABLES = 5
MAX_FILES = 5
MIN_TABLE_SCORE = 3.0
MIN_FILE_SCORE = 2.0
_LOOKUP_ROLES = frozenset({"lookup", "dimension"})
_LINE_SUFFIXES = ("_lines", "_line", "_items", "_item")


def _header_line_companions(selected: list[str], known_tables: list[str]) -> list[str]:
    """Keep header/line table pairs together (e.g. finance_ap_bills + finance_ap_bill_lines)."""
    known_map = {n.lower(): n for n in known_tables}
    extra: list[str] = []
    selected_l = {s.lower() for s in selected}

    def add(cand: str) -> None:
        orig = known_map.get(cand.lower())
        if orig and orig.lower() not in selected_l and orig not in extra:
            extra.append(orig)

    for name in list(selected_l):
        add(name + "_lines")
        add(name + "_line")
        add(name + "_items")
        if name.endswith("s") and not name.endswith("ss"):
            stem = name[:-1]
            for suffix in _LINE_SUFFIXES:
                add(stem + suffix)
        for suffix in _LINE_SUFFIXES:
            if name.endswith(suffix):
                stem = name[: -len(suffix)]
                add(stem)
                add(stem + "s")
    return extra


def _question_tokens(question: str) -> set[str]:
    routing_question, _ = correct_query_spelling(question, build_vocabulary())
    tokens = {t for t in re.findall(r"[a-z0-9]+", routing_question.lower()) if len(t) > 2}
    tokens.update(t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2)
    return tokens


@dataclass
class ResolvedCatalogScope:
    """Tables/files/columns identified from catalog metadata (not content chunks)."""

    table_names: list[str] = field(default_factory=list)
    file_names: list[str] = field(default_factory=list)
    column_hints: list[str] = field(default_factory=list)
    method: str = "none"
    confidence: float = 0.0


def _score_table(
    question_tokens: set[str],
    table: dict[str, Any],
    columns: list[dict[str, Any]],
    *,
    source_boost: float = 0.0,
) -> tuple[float, list[str]]:
    score = source_boost
    hints: list[str] = []
    vocab = build_vocabulary()
    table_name = (table.get("table_name") or "").lower()
    role = (table.get("table_role") or "fact").lower()

    if role == "fact":
        score += 1.0
    elif role in _LOOKUP_ROLES:
        score += 0.25

    if table_name in question_tokens or table_name.replace("_", " ") in " ".join(question_tokens):
        score += 6.0
    for part in table_name.split("_"):
        if len(part) > 2 and part in question_tokens:
            score += 2.5
        elif len(part) > 2 and fuzzy_token_matches(part, question_tokens, vocab):
            score += 1.5

    definition = (table.get("definition") or "").lower()
    for tok in question_tokens:
        if tok in definition:
            score += 0.5

    for col in columns:
        col_name = (col.get("column_name") or "").lower()
        if not col_name:
            continue
        col_score = 0.0
        if col_name in question_tokens:
            col_score += 4.0
            hints.append(col["column_name"])
        for part in col_name.split("_"):
            if len(part) > 2 and part in question_tokens:
                col_score += 2.0
                if col["column_name"] not in hints:
                    hints.append(col["column_name"])
        for label in col.get("labels") or []:
            label_low = str(label).lower()
            for part in re.split(r"[\s_]+", label_low):
                if len(part) > 2 and part in question_tokens:
                    col_score += 2.5
                    if col["column_name"] not in hints:
                        hints.append(col["column_name"])
        desc = (col.get("description") or "").lower()
        for tok in question_tokens:
            if tok in desc:
                col_score += 0.75
                if col_score >= 2.0 and col["column_name"] not in hints:
                    hints.append(col["column_name"])
        score += col_score

    return score, hints


def resolve_table_scope(
    question: str,
    *,
    domain_id: str,
    source_id: str | None = None,
    max_tables: int = MAX_TABLES,
) -> ResolvedCatalogScope:
    """Score postgres tables in a domain by name/column metadata; return top matches."""
    tokens = _question_tokens(question)
    if not tokens:
        return ResolvedCatalogScope()

    scored: list[tuple[float, str, list[str], str]] = []
    lookup_tables: list[str] = []

    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if not is_structured_sql_connector(source.get("connector")):
            continue
        boost = 2.0 if source_id and source["id"] == source_id else 0.0
        for table in list_table_metadata(source["id"]):
            if not table.get("enabled", True):
                continue
            role = (table.get("table_role") or "fact").lower()
            if role == "excluded":
                continue
            tname = table["table_name"]
            if role in _LOOKUP_ROLES:
                lookup_tables.append(tname)
            cols = list_column_metadata(table["id"])
            table_score, hints = _score_table(tokens, table, cols, source_boost=boost)
            if table_score > 0:
                scored.append((table_score, tname, hints, role))

    if not scored:
        return ResolvedCatalogScope()

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score = scored[0][0]
    if best_score < MIN_TABLE_SCORE:
        return ResolvedCatalogScope(method="below_threshold", confidence=0.0)

    cutoff = best_score * 0.45
    selected: list[str] = []
    all_hints: list[str] = []
    for table_score, tname, hints, role in scored:
        if role in _LOOKUP_ROLES:
            continue
        if len(selected) >= max_tables:
            break
        if table_score >= cutoff:
            if tname not in selected:
                selected.append(tname)
            for hint in hints:
                if hint not in all_hints:
                    all_hints.append(hint)

    known_tables = [row[1] for row in scored] + lookup_tables
    for tname in _header_line_companions(selected, known_tables):
        selected.append(tname)

    # Lookups (channels, countries, …) must stay available for joins even when
    # fact-table narrowing already filled MAX_TABLES.
    for tname in lookup_tables:
        if tname not in selected and selected:
            selected.append(tname)

    confidence = min(1.0, best_score / (best_score + (scored[1][0] if len(scored) > 1 else 0) + 1.0))
    return ResolvedCatalogScope(
        table_names=selected,
        column_hints=all_hints[:8],
        method="metadata_tables",
        confidence=confidence,
    )


def resolve_file_scope(
    question: str,
    source_id: str,
    *,
    max_files: int = MAX_FILES,
) -> ResolvedCatalogScope:
    """Score unstructured files by filename and RAG metadata."""
    source = get_source(source_id=source_id)
    if not source:
        return ResolvedCatalogScope()

    tokens = _question_tokens(question)
    if not tokens:
        return ResolvedCatalogScope()

    rag_settings = {
        row["file_name"]: bool(row.get("rag_enabled", True))
        for row in list_source_file_rag(source_id)
    }
    scored: list[tuple[float, str]] = []
    vocab = build_vocabulary()

    for path in list_source_files(source):
        name = path.name
        if rag_settings and not rag_settings.get(name, True):
            continue
        score = 0.0
        stem = path.stem.lower()
        name_low = name.lower()
        for tok in tokens:
            if tok in name_low or tok in stem:
                score += 3.0
            elif fuzzy_token_matches(tok, {stem, name_low.replace(".", " ")}, vocab):
                score += 2.0
        for part in re.split(r"[_\-.]+", stem):
            if len(part) > 2 and part in tokens:
                score += 2.0
        if score > 0:
            scored.append((score, name))

    if not scored:
        return ResolvedCatalogScope()

    scored.sort(key=lambda row: row[0], reverse=True)
    best_score = scored[0][0]
    if best_score < MIN_FILE_SCORE:
        return ResolvedCatalogScope(method="below_threshold", confidence=0.0)

    cutoff = best_score * 0.5
    selected = [name for score, name in scored if score >= cutoff][:max_files]
    confidence = min(1.0, best_score / (best_score + (scored[1][0] if len(scored) > 1 else 0) + 1.0))
    return ResolvedCatalogScope(
        file_names=selected,
        method="metadata_files",
        confidence=confidence,
    )


def resolve_catalog_scope(
    question: str,
    *,
    domain_id: str | None,
    source_id: str | None,
    rag_source_id: str | None,
    execution_kind: str,
    embedder=None,
) -> ResolvedCatalogScope:
    """Resolve table/file/column scope from catalog metadata for the chosen execution path."""
    del embedder  # reserved for future embedding-based table/file tie-breaks

    if not domain_id:
        return ResolvedCatalogScope()

    table_scope = ResolvedCatalogScope()
    file_scope = ResolvedCatalogScope()

    if execution_kind in ("sql", "hybrid"):
        table_scope = resolve_table_scope(
            question,
            domain_id=domain_id,
            source_id=source_id,
        )

    rag_sid = rag_source_id or (source_id if execution_kind == "rag" else None)
    if execution_kind in ("rag", "hybrid") and rag_sid:
        rag_source = get_source(source_id=rag_sid)
        if rag_source:
            if rag_source.get("source_type") == "structured":
                structured_tables = resolve_table_scope(
                    question,
                    domain_id=domain_id,
                    source_id=rag_sid,
                )
                if structured_tables.table_names:
                    table_scope = _merge_scopes(table_scope, structured_tables)
            else:
                file_scope = resolve_file_scope(question, rag_sid)

    if not table_scope.table_names and not file_scope.file_names:
        method = "none"
        confidence = 0.0
    elif table_scope.table_names and file_scope.file_names:
        method = "metadata_tables+files"
        confidence = max(table_scope.confidence, file_scope.confidence)
    elif table_scope.table_names:
        method = table_scope.method
        confidence = table_scope.confidence
    else:
        method = file_scope.method
        confidence = file_scope.confidence

    column_hints = list(dict.fromkeys(table_scope.column_hints))[:8]
    return ResolvedCatalogScope(
        table_names=table_scope.table_names,
        file_names=file_scope.file_names,
        column_hints=column_hints,
        method=method,
        confidence=confidence,
    )


def _merge_scopes(a: ResolvedCatalogScope, b: ResolvedCatalogScope) -> ResolvedCatalogScope:
    tables = list(dict.fromkeys(a.table_names + b.table_names))
    hints = list(dict.fromkeys(a.column_hints + b.column_hints))[:8]
    return ResolvedCatalogScope(
        table_names=tables,
        file_names=a.file_names or b.file_names,
        column_hints=hints,
        method="metadata_tables",
        confidence=max(a.confidence, b.confidence),
    )


def chunk_source_files_for_scope(
    *,
    domain_id: str | None,
    source_id: str | None,
    table_names: list[str] | None,
    file_names: list[str] | None,
) -> list[str]:
    """Map resolved tables/files to knowledge_chunks source_file paths for scoped search."""
    paths: list[str] = []
    table_set = set(table_names or [])
    file_set = set(file_names or [])

    if domain_id and table_set:
        for source in list_sources(domain_id=domain_id, enabled_only=True):
            if not is_structured_sql_connector(source.get("connector")):
                continue
            domain_slug = source.get("domain_slug") or "domain"
            source_slug = source.get("slug") or "ds"
            for table in list_table_metadata(source["id"]):
                tname = table["table_name"]
                if tname not in table_set:
                    continue
                paths.append(f"{CATALOG_SOURCE_PREFIX}{domain_slug}/{source_slug}/{tname}")
                paths.append(f"{LOOKUP_SOURCE_PREFIX}{domain_slug}/{source_slug}/{tname}")

    if source_id and file_set:
        source = get_source(source_id=source_id)
        slug = (source or {}).get("slug") or "dataset"
        for name in file_set:
            paths.append(name)
        paths.append(f"{slug}_instructions")

    return list(dict.fromkeys(paths))
