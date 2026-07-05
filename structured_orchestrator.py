"""
Structured-data query orchestration (Phase 2+) — SQL path.

For Python/CSV curation see code_orchestrator.py.

Target flow (postgres):

  1. Domain routing      → domain_router.route_question()
  2. Dataset selection   → pick postgres dataset in that domain
  3. Schema grounding    → table definitions + column labels from catalog
  4. LLM generates read-only SQL
  5. Execute on demand   → dataset connection (read-only DB user)
  6. Curated rows        → answer LLM (+ optional UI table)

Catalog metadata is the source of truth for step 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from catalog_db import (
    get_source,
    list_column_metadata,
    list_columns_by_source,
    list_sources,
    list_table_metadata,
)
from sql_sanitize import has_multiple_sql_statements, normalize_llm_sql
from catalog_definition import load_definition_for_prompt, prepare_definition_for_llm
from dataset_router import pick_structured_dataset as _pick_structured_dataset
from domain_router import route_question
from api.answer_format import build_sql_summary_prompt
from serde import coerce_json_rows
from sql_dialect import dialect_for_connector, dialect_label, prepare_sql_for_execution
from structured_sql import is_structured_sql_connector
from structured_db import postgres_config_from_source

RetrievalMode = Literal["unstructured", "structured", "hybrid"]

# User wants executed data (SQL), not catalog tour / query tips.
_DATA_REQUEST_PATTERNS = re.compile(
    r"\b("
    r"give me|get me|show me|let me see|can you show|can you give|can you get|can you list|"
    r"pull up|pull|fetch|display|return|find me|list|report on|"
    r"how many|count|total|sum|average|avg|min|max|top \d+|"
    r"breakdown|break down|trend|compare|distribution|"
    r"between|per month|per year|group by"
    r")\b",
    re.I,
)

# Backward-compatible alias used by code_orchestrator.
_ANALYTICAL_PATTERNS = _DATA_REQUEST_PATTERNS

# User wants recommendations / how-to / schema help — not row results.
_GUIDANCE_PATTERNS = re.compile(
    r"\b("
    r"how (?:do I|to|can I|should I) (?:query|find|get|use|write|run|build|access)|"
    r"what (?:tables?|fields?|columns?|schema) (?:should|can|do|are|exist|available)|"
    r"which (?:table|field|column|dataset)|"
    r"recommend(?:ation)?s?|suggest(?:ion)?s? how|guide me (?:on|how)|"
    r"help me (?:query|find|understand how|write)|"
    r"data dictionary|schema overview|"
    r"explain (?:the )?(?:schema|data model|table structure|how (?:to|I can) query)"
    r")\b",
    re.I,
)

_DESCRIPTIVE_STRUCTURED_PATTERNS = re.compile(
    r"\b(info about|information about|tell me about|describe|overview|high level|"
    r"what is|what are|explain|details on|summary of|give me.*about)\b",
    re.I,
)


def table_mentioned_in_question(table_name: str, question: str) -> bool:
    """True when the question likely refers to a cataloged table name."""
    q_lower = question.lower()
    tname = table_name.lower()
    if tname in q_lower or tname.replace("_", " ") in q_lower:
        return True
    parts = [p for p in tname.split("_") if len(p) > 2]
    return len(parts) >= 2 and all(p in q_lower for p in parts)


def question_references_catalog_tables(question: str, domain_id: str) -> bool:
    """True when the question mentions a postgres table cataloged in this domain."""
    from routing_cache import get_cached_routing_context

    for domain in get_cached_routing_context():
        if domain["id"] != domain_id:
            continue
        for source in domain.get("sources") or []:
            if not is_structured_sql_connector(source.get("connector")):
                continue
            for table_name in source.get("table_names") or []:
                if table_mentioned_in_question(table_name, question):
                    return True
        return False

    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if not is_structured_sql_connector(source.get("connector")):
            continue
        for table in list_table_metadata(source["id"]):
            if table_mentioned_in_question(table["table_name"], question):
                return True
    return False


@dataclass
class StructuredDomainMatch:
    """Best structured postgres domain for a question (dict-like for legacy callers)."""

    domain: dict | None
    score: int = 0
    dataset: dict | None = None

    def __bool__(self) -> bool:
        return self.domain is not None

    def __getitem__(self, key: str) -> Any:
        if self.domain is None:
            raise KeyError(key)
        return self.domain[key]

    def get(self, key: str, default: Any = None) -> Any:
        if self.domain is None:
            return default
        return self.domain.get(key, default)

    def __iter__(self):
        yield self.domain
        yield self.score
        yield self.dataset


def score_structured_domain_fit(
    question: str, domain_id: str, embedder=None
) -> tuple[int, dict | None]:
    """Higher score = better structured postgres match. Returns (score, best dataset)."""
    if not should_use_structured_sql(question, domain_id):
        return 0, None
    dataset = pick_structured_dataset(question, domain_id, embedder)
    if not dataset:
        return 0, None

    score = 1
    q_lower = question.lower()
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2}
    dname = dataset.get("name", "").lower()
    for tok in q_tokens:
        if tok in dname:
            score += 3

    from routing_cache import get_cached_routing_context

    table_names: list[str] = []
    for domain in get_cached_routing_context():
        if domain["id"] != domain_id:
            continue
        for source in domain.get("sources") or []:
            if source["id"] == dataset["id"]:
                table_names = source.get("table_names") or []
                break
    if not table_names:
        for table in list_table_metadata(dataset["id"]):
            table_names.append(table["table_name"])
    for tname in table_names:
        tname = tname.lower()
        if tname in q_lower or tname.replace("_", " ") in q_lower:
            score += 5
        for part in tname.split("_"):
            if len(part) > 2 and part in q_tokens:
                score += 2
    return score, dataset


def find_best_structured_domain(
    question: str,
    embedder=None,
    *,
    prefer_domain_id: str | None = None,
    allowed_domain_ids: list[str] | None = None,
) -> StructuredDomainMatch:
    """Return the best structured postgres domain, score, and dataset for this question."""
    from catalog_db import get_domain
    from routing_cache import get_cached_routing_context

    q_tokens = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}

    def _score_domain(domain_id: str, boost: int = 0) -> tuple[int, dict | None]:
        score, dataset = score_structured_domain_fit(question, domain_id, embedder)
        return score + boost, dataset

    # Fast path: keyword-routed domain with a strong table/name match.
    if prefer_domain_id:
        prefer_score, prefer_dataset = _score_domain(prefer_domain_id, boost=1)
        if prefer_score >= 5:
            domain = get_domain(domain_id=prefer_domain_id)
            return StructuredDomainMatch(domain, prefer_score, prefer_dataset)

    best: dict | None = None
    best_dataset: dict | None = None
    best_score = 0
    domains = get_cached_routing_context()
    if allowed_domain_ids:
        allowed = set(allowed_domain_ids)
        domains = [domain for domain in domains if domain["id"] in allowed]
    if not domains:
        return StructuredDomainMatch(None)
    ordered = sorted(
        domains,
        key=lambda d: (
            0
            if d["id"] == prefer_domain_id
            else 1
            if q_tokens & _tokenize_domain(d)
            else 2
        ),
    )
    for domain in ordered:
        boost = 1 if domain["id"] == prefer_domain_id else 0
        score, dataset = _score_domain(domain["id"], boost=boost)
        if score > best_score:
            best_score = score
            best = domain
            best_dataset = dataset
        if score >= 8 and domain["id"] == prefer_domain_id:
            break
        if best_score >= 10:
            break
    if best_score > 0:
        return StructuredDomainMatch(best, best_score, best_dataset)
    return StructuredDomainMatch(None)


def _tokenize_domain(domain: dict) -> set[str]:
    parts = [domain.get("name", ""), domain.get("description", ""), domain.get("slug", "")]
    for source in domain.get("sources") or []:
        parts.append(source.get("name", ""))
        for table_name in source.get("table_names") or []:
            parts.extend(table_name.replace("_", " ").split())
    return {t for t in re.findall(r"[a-z0-9]+", " ".join(parts).lower()) if len(t) > 2}


def should_use_structured_sql(question: str, domain_id: str | None) -> bool:
    """Route to SQL when the user wants data rows, not query/schema guidance."""
    if not domain_id:
        return False
    structured = list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
    structured_sources = [s for s in structured if is_structured_sql_connector(s.get("connector"))]
    if not structured_sources:
        return False
    if _GUIDANCE_PATTERNS.search(question):
        return False
    if _DATA_REQUEST_PATTERNS.search(question):
        return True
    if question_references_catalog_tables(question, domain_id):
        return True
    if _DESCRIPTIVE_STRUCTURED_PATTERNS.search(question):
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}
        for source in structured_sources:
            for table in list_table_metadata(source["id"]):
                for part in table["table_name"].lower().split("_"):
                    if len(part) > 2 and part in q_tokens:
                        return True
    return False


@dataclass
class StructuredSchemaContext:
    """Everything an LLM needs to generate correct SQL for one dataset."""

    source_id: str
    source_name: str
    domain_id: str
    domain_name: str
    connector: str
    dataset_definition_md: str
    tables: list[dict[str, Any]] = field(default_factory=list)
    trino_catalog: str = ""

    def qualified_relation(self, table: dict[str, Any]) -> str:
        schema = table["table_schema"]
        name = table["table_name"]
        if self.connector == "trino" and self.trino_catalog:
            return f"{self.trino_catalog}.{schema}.{name}"
        return f"{schema}.{name}"

    def cataloged_relations(self) -> list[str]:
        return [self.qualified_relation(t) for t in self.tables]

    def _active_tables(self) -> list[dict[str, Any]]:
        return [
            t
            for t in self.tables
            if t.get("enabled", True) and (t.get("table_role") or "fact") != "excluded"
        ]

    def table_business_rules_block(self) -> str:
        """Per-table definitions from catalog metadata (filters, status values, metric rules)."""
        blocks: list[str] = []
        for table in self._active_tables():
            table_def = (table.get("definition") or "").strip()
            if not table_def:
                continue
            rel = self.qualified_relation(table)
            blocks.append(f"### `{rel}`\n{table_def}")
        if not blocks:
            return ""
        return (
            "## Table business rules\n"
            "Authoritative per-table guidance from the catalog — apply exactly in SQL and answers "
            "(status filters, revenue definitions, exclusions, join hints).\n\n"
            + "\n\n".join(blocks)
        )

    def to_llm_prompt_block(self) -> str:
        relations = [self.qualified_relation(t) for t in self._active_tables()]
        definition = prepare_definition_for_llm(self.dataset_definition_md)
        lines = [
            f"# Dataset: {self.source_name}",
            f"Domain: {self.domain_name}",
            f"Connector: {self.connector}",
            f"SQL dialect: {dialect_label(dialect_for_connector(self.connector))}",
            "",
            "## Allowed tables (use ONLY these exact schema-qualified names)",
        ]
        if relations:
            for rel in relations:
                lines.append(f"- `{rel}`")
        else:
            lines.append("- (no tables cataloged — cannot generate SQL)")
        lines.extend(
            [
                "",
                "Do NOT invent table or column names (e.g. use `customer_profiles`, not `customers`).",
                "",
                "## Dataset definition",
                "Authoritative for dataset scope, documented table relationships (hub/bridge tables), "
                "analytics patterns, and caveats.",
                "Join paths describe how real catalog tables connect — they are not table names.",
                "Read this before writing SQL — prefer documented relationships over guessing foreign keys.",
                "",
                definition,
            ]
        )
        table_rules = self.table_business_rules_block()
        if table_rules:
            lines.extend(["", table_rules])
        lines.extend(
            [
                "",
                "## Column reference (exact names and types)",
            ]
        )
        for table in self._active_tables():
            role = table.get("table_role") or "fact"
            lines.append(f"### {self.qualified_relation(table)} (role: {role})")
            table_def = (table.get("definition") or "").strip()
            if table_def:
                lines.append(
                    "*(Business rules for this table are in **Table business rules** above — "
                    "follow them for filters and metrics.)*"
                )
            lines.append("Columns:")
            columns = table.get("columns") or []
            if not columns:
                lines.append("- (no columns cataloged)")
            for col in columns:
                labels = ", ".join(col.get("labels") or [])
                desc = (col.get("description") or "").strip()
                extra = ""
                if labels:
                    extra += f" labels: [{labels}]"
                if desc:
                    extra += f" — {desc}"
                lines.append(
                    f"- `{col['column_name']}` ({col.get('data_type', '?')}){extra}".strip()
                )
            lines.append("")
        lines.append(
            "SQL rules: READ-ONLY SELECT only; schema-qualify every table; use Column reference "
            "for exact column names and labels; follow Dataset definition relationships and Table "
            "business rules for filters/status values; do not invent tables such as paths or "
            "join_paths; LIMIT rows unless the user requests a full export."
        )
        return "\n".join(lines)


@dataclass
class StructuredQueryPlan:
    """LLM output + execution metadata (future)."""

    question: str
    domain_id: str | None
    source_id: str
    sql: str
    schema_context: StructuredSchemaContext
    routing: dict[str, Any]


@dataclass
class StructuredQueryResult:
    plan: StructuredQueryPlan
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    summary_prompt: str  # fed to LLM for natural-language answer


def classify_retrieval_mode(
    question: str,
    *,
    domain_id: str | None,
    routing: dict[str, Any] | None = None,
) -> RetrievalMode:
    """
    Decide unstructured RAG vs structured SQL vs both.
    Heuristic MVP — replace with LLM classifier when ready.
    """
    if not domain_id:
        return "unstructured"

    structured = list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
    unstructured = list_sources(domain_id=domain_id, source_type="unstructured", enabled_only=True)

    if not structured:
        return "unstructured"
    if not unstructured:
        return "structured"

    if should_use_structured_sql(question, domain_id):
        return "structured"
    if routing and routing.get("confidence", 0) < 0.4:
        return "hybrid"
    return "unstructured"


def pick_structured_dataset(
    question: str,
    domain_id: str,
    embedder=None,
    *,
    query_vector=None,
    chunks: list[dict] | None = None,
) -> dict | None:
    """Choose the best postgres dataset in a domain by metadata + optional chunk signals."""
    return _pick_structured_dataset(
        question,
        domain_id,
        embedder,
        query_vector=query_vector,
        chunks=chunks,
    )


def load_table_business_rules_for_domain(domain_id: str | None) -> str:
    """Collect table business rules from all structured postgres datasets in a domain."""
    if not domain_id:
        return ""
    parts: list[str] = []
    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if not is_structured_sql_connector(source.get("connector")):
            continue
        try:
            block = build_schema_context(source["id"]).table_business_rules_block()
        except Exception:
            continue
        if block:
            parts.append(f"### Dataset: {source['name']}\n\n{block}")
    return "\n\n".join(parts).strip()


def build_schema_context(
    source_id: str,
    *,
    table_names: list[str] | None = None,
) -> StructuredSchemaContext:
    """Assemble catalog metadata for LLM SQL generation."""
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")

    allowed = {t.lower() for t in table_names} if table_names else None
    columns_by_table = list_columns_by_source(source_id)
    tables_out: list[dict[str, Any]] = []
    for table in list_table_metadata(source_id):
        if not table.get("enabled", True):
            continue
        if (table.get("table_role") or "fact") == "excluded":
            continue
        if allowed is not None and table["table_name"].lower() not in allowed:
            continue
        tables_out.append(
            {
                **table,
                "columns": columns_by_table.get(table["id"], []),
            }
        )

    cfg = source.get("config") or {}
    trino_catalog = (cfg.get("catalog") or cfg.get("trino_catalog") or "").strip()

    return StructuredSchemaContext(
        source_id=source_id,
        source_name=source["name"],
        domain_id=source["domain_id"],
        domain_name=source.get("domain_name", ""),
        connector=source["connector"],
        dataset_definition_md=load_definition_for_prompt(source),
        tables=tables_out,
        trino_catalog=trino_catalog,
    )


def build_domain_schema_context(
    domain_id: str,
    primary_source_id: str,
    *,
    table_names: list[str] | None = None,
) -> StructuredSchemaContext:
    """Postgres tables in a domain — optionally narrowed to table_names."""
    primary = get_source(source_id=primary_source_id)
    if not primary:
        raise ValueError(f"Dataset not found: {primary_source_id}")

    allowed = {t.lower() for t in table_names} if table_names else None
    definition_parts: list[str] = []
    tables_out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if not is_structured_sql_connector(source.get("connector")):
            continue
        def_md = load_definition_for_prompt(source)
        if def_md.strip() and def_md != "(none)":
            definition_parts.append(f"### {source['name']}\n{def_md}")
        columns_by_table = list_columns_by_source(source["id"])
        for table in list_table_metadata(source["id"]):
            if not table.get("enabled", True):
                continue
            if (table.get("table_role") or "fact") == "excluded":
                continue
            if allowed is not None and table["table_name"].lower() not in allowed:
                continue
            key = (table["table_schema"], table["table_name"])
            if key in seen:
                continue
            seen.add(key)
            tables_out.append({**table, "columns": columns_by_table.get(table["id"], [])})

    tables_out.sort(key=lambda t: (t["table_schema"], t["table_name"]))
    return StructuredSchemaContext(
        source_id=primary_source_id,
        source_name=primary["name"],
        domain_id=domain_id,
        domain_name=primary.get("domain_name", ""),
        connector=primary.get("connector") or "trino",
        dataset_definition_md="\n\n".join(definition_parts),
        tables=tables_out,
        trino_catalog=(primary.get("config") or {}).get("catalog")
        or (primary.get("config") or {}).get("trino_catalog")
        or "",
    )


def _normalize_sql_for_validation(sql: str) -> str:
    text = sql.strip().rstrip(";")
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text.strip().lower()


def validate_readonly_sql(sql: str) -> None:
    """Reject anything that is not a single read-only SELECT (WITH ... SELECT is allowed)."""
    normalized = _normalize_sql_for_validation(sql)
    if not (normalized.startswith("select") or normalized.startswith("with")):
        raise ValueError("Only SELECT statements are allowed")
    if normalized.startswith("with") and not re.search(r"\bselect\b", normalized):
        raise ValueError("Only SELECT statements are allowed")
    forbidden = (
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "execute",
        ";",  # no multi-statement
    )
    for token in forbidden:
        if token == ";":
            continue
        if re.search(rf"\b{token}\b", normalized):
            raise ValueError(f"Forbidden SQL keyword: {token}")
    if has_multiple_sql_statements(sql):
        raise ValueError("Multiple statements are not allowed")


@dataclass
class SqlValidationResult:
    """Result of the pre-execution SQL validation gate."""

    valid: bool
    violations: list[str] = field(default_factory=list)
    phantom_tables: list[str] = field(default_factory=list)
    phantom_columns: list[str] = field(default_factory=list)

    @property
    def is_catalog_violation(self) -> bool:
        """True when SQL references tables not in the catalog — trigger repair."""
        return bool(self.phantom_tables)


def _neutralize_function_from_keywords(sql: str) -> str:
    """Prevent EXTRACT(x FROM col) and similar from being parsed as table refs."""
    text = sql

    def _replace_inner_from(match: re.Match[str]) -> str:
        return re.sub(r"\sfrom\s", " __expr__ ", match.group(0), flags=re.I)

    for func in ("extract", "substring", "trim", "translate", "position", "overlay"):
        text = re.sub(rf"\b{func}\s*\([^)]*\)", _replace_inner_from, text, flags=re.I)
    return text


def _extract_sql_identifiers(sql: str) -> tuple[set[str], set[str]]:
    """
    Extract table references and selected column identifiers from SQL text.
    Returns (table_refs, column_refs) as lowercase name sets (unqualified).
    Best-effort — regex-based, not a full parser.
    """
    normalized = _neutralize_function_from_keywords(sql.lower())

    # Table references: FROM/JOIN with optional catalog.schema.table qualification (Trino).
    table_pattern = re.compile(
        r"(?:from|join)\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)"
        r"(?:\s+(?:as\s+)?[a-z_][a-z0-9_]*)?",
        re.I,
    )
    table_refs: set[str] = set()
    for match in table_pattern.finditer(normalized):
        parts = match.group(1).lower().split(".")
        table_refs.add(parts[-1])

    # Column references: simple name.col or bare col in SELECT list (before FROM)
    from_pos = normalized.find("from")
    select_clause = normalized[6:from_pos] if from_pos > 0 else ""
    col_pattern = re.compile(r"(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)")
    col_refs = {
        m.group(1).lower()
        for m in col_pattern.finditer(select_clause)
        if m.group(1) not in {"select", "distinct", "as", "case", "when", "then", "else", "end"}
    }

    return table_refs, col_refs


def _matches_catalog_table_name(name: str, allowed_table_names: set[str]) -> bool:
    """Accept exact catalog names and unambiguous suffix aliases (e.g. invoices → sales_invoices)."""
    if name in allowed_table_names:
        return True
    suffix_matches = [t for t in allowed_table_names if t.endswith(f"_{name}")]
    return len(suffix_matches) == 1


def validate_generated_sql(
    sql: str,
    schema_context: "StructuredSchemaContext",
) -> SqlValidationResult:
    """
    Explicit pre-execution validation gate — runs before hitting the database.

    Checks:
    1. Read-only / syntax (via validate_readonly_sql)
    2. All table references are in the catalog Allowed tables
    3. Selected columns exist in at least one cataloged table (best-effort)

    Returns SqlValidationResult; callers use .is_catalog_violation to decide
    whether to trigger repair before the first DB round-trip.
    """
    phantom_tables: list[str] = []
    phantom_columns: list[str] = []

    # Gate 1: read-only syntax
    try:
        validate_readonly_sql(sql)
    except ValueError as exc:
        return SqlValidationResult(valid=False, violations=[str(exc)])

    if not schema_context or not schema_context.tables:
        return SqlValidationResult(valid=True)

    # Build catalog name sets
    allowed_table_names = {t["table_name"].lower() for t in schema_context.tables}
    all_column_names: set[str] = set()
    for table in schema_context.tables:
        for col in table.get("columns") or []:
            all_column_names.add(col["column_name"].lower())

    # Gate 2: catalog table check
    sql_tables, sql_cols = _extract_sql_identifiers(sql)
    # Filter out SQL keywords and aliases that look like table names
    sql_keywords = {
        "select", "from", "where", "join", "inner", "outer", "left", "right",
        "full", "cross", "on", "and", "or", "not", "in", "as", "by", "group",
        "order", "having", "limit", "offset", "union", "all", "distinct",
        "null", "true", "false", "case", "when", "then", "else", "end",
        "count", "sum", "avg", "min", "max", "coalesce", "cast", "extract",
        "date", "now", "interval", "asc", "desc", "the", "this", "that", "with",
    }
    candidate_tables = sql_tables - sql_keywords
    allowed_schemas = {t.get("table_schema", "").lower() for t in schema_context.tables}
    if schema_context.trino_catalog:
        allowed_schemas.add(schema_context.trino_catalog.lower())
    catalog_violations: list[str] = []
    for tname in candidate_tables:
        if tname in allowed_schemas:
            continue
        if not _matches_catalog_table_name(tname, allowed_table_names):
            # EXTRACT(... FROM col) and similar can still leak column names here.
            if tname in all_column_names:
                continue
            phantom_tables.append(tname)
            catalog_violations.append(f"Table `{tname}` is not in the catalog Allowed tables")

    # Gate 3: column check (warn only — aliases make strict checking unreliable)
    candidate_cols = sql_cols - sql_keywords - allowed_table_names
    for cname in candidate_cols:
        if len(cname) <= 2:  # skip short tokens (a, id, etc.)
            continue
        if cname not in all_column_names:
            phantom_columns.append(cname)

    return SqlValidationResult(
        valid=True,
        violations=catalog_violations,
        phantom_tables=phantom_tables,
        phantom_columns=phantom_columns,
    )


def _is_recoverable_sql_error(message: str) -> bool:
    lower = message.lower()
    return (
        "does not exist" in lower
        or "42p01" in lower
        or "undefined column" in lower
        or "42703" in lower
        or "ambiguous" in lower
        or "type_mismatch" in lower
        or "cannot apply operator" in lower
        or "cannot be applied to" in lower
    )


def _revalidate_sql_after_repair(
    sql: str,
    schema_context: "StructuredSchemaContext",
    *,
    repair_label: str,
) -> str:
    """Run validation after repair_sql; raise if still invalid."""
    sql = normalize_llm_sql(sql)
    recheck = validate_generated_sql(sql, schema_context)
    if not recheck.valid:
        raise ValueError(
            f"SQL still invalid after {repair_label}: {'; '.join(recheck.violations)}"
        )
    if recheck.phantom_tables:
        raise ValueError(
            f"SQL still references tables not in the catalog after {repair_label}: "
            + ", ".join(f"`{t}`" for t in recheck.phantom_tables)
        )
    return sql


def generate_and_execute_readonly_sql(
    question: str,
    source_id: str,
    schema_context: StructuredSchemaContext,
    *,
    model: str,
    backend: str = "mistral",
    base_url: str = "http://localhost:11434",
    max_attempts: int = 2,
    rag_chunks: list[dict[str, Any]] | None = None,
    mcp_supplement: str = "",
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str], list[list[Any]], list[str]]:
    """Generate SQL from catalog schema, execute, retry on errors, then partial fallback."""
    from api.llm import generate_partial_sql, generate_sql, repair_sql
    from api.schema_gaps import analyze_schema_gaps, note_from_sql_error
    from hybrid_prompt import build_sql_rag_supplement, merge_generation_supplements, prioritize_chunks
    from structured_follow_up import (
        apply_structured_transform,
        extract_prior_structured_result,
        plan_structured_follow_up,
    )

    if not schema_context.tables:
        raise ValueError(
            "No tables are cataloged for this dataset. Open Data Catalog → dataset → "
            "Data tab → discover and add tables before running analytics."
        )

    history = conversation_history or []
    prior = extract_prior_structured_result(history) if history else None
    active_question = question
    chat_history = [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")]

    if prior and len(history) >= 2:
        follow_up = plan_structured_follow_up(
            question,
            history,
            prior,
            model=model,
            backend=backend,
            base_url=base_url,
        )
        if follow_up.notes:
            notes_from_plan = list(follow_up.notes)
        else:
            notes_from_plan = []
        if follow_up.mode == "transform" and follow_up.transform_spec:
            columns, rows = apply_structured_transform(prior, follow_up.transform_spec)
            return prior.sql or "", columns, rows, notes_from_plan
        active_question = follow_up.refined_question
    else:
        notes_from_plan = []

    gap_analysis = analyze_schema_gaps(active_question, schema_context)
    notes: list[str] = notes_from_plan + list(gap_analysis.notes)
    gap_instructions = gap_analysis.skip_instructions + gap_analysis.join_hints
    rag_supplement = merge_generation_supplements(
        build_sql_rag_supplement(prioritize_chunks(rag_chunks or [])),
        mcp_supplement,
    )
    errors: list[str] = []

    sql = normalize_llm_sql(
        generate_sql(
            active_question,
            schema_context,
            model=model,
            backend=backend,
            base_url=base_url,
            gap_instructions=gap_instructions,
            rag_supplement=rag_supplement,
            conversation_history=chat_history,
            prior_result=prior,
        )
    )

    # ── Explicit pre-execution validation gate ──────────────────────────────
    # Catch syntax/catalog violations before the DB round-trip; repair before executing.
    validation = validate_generated_sql(sql, schema_context)
    if not validation.valid or validation.is_catalog_violation:
        if not validation.valid:
            violation_text = f"SQL validation failed: {'; '.join(validation.violations)}"
        else:
            phantom_note = (
                "SQL referenced tables not in the catalog — repaired before execution."
            )
            if phantom_note not in notes:
                notes.append(phantom_note)
            violation_text = (
                "Validation error — tables not in catalog: "
                + ", ".join(f"`{t}`" for t in validation.phantom_tables)
            )
        errors.append(violation_text)
        sql = repair_sql(
            active_question,
            schema_context,
            sql,
            violation_text,
            model=model,
            backend=backend,
            base_url=base_url,
            gap_instructions=gap_instructions,
            rag_supplement=rag_supplement,
            conversation_history=chat_history,
            prior_result=prior,
        )
        sql = _revalidate_sql_after_repair(sql, schema_context, repair_label="repair")
    # ────────────────────────────────────────────────────────────────────────

    source = get_source(source_id=source_id)
    if source:
        sql = prepare_sql_for_execution(sql, source.get("connector"))

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            columns, rows = execute_readonly_sql(source_id, sql)
            return sql, columns, rows, notes
        except Exception as exc:
            last_exc = exc
            err_text = str(exc)
            errors.append(err_text)
            err_note = note_from_sql_error(err_text)
            if err_note and err_note not in notes:
                notes.append(err_note)
            if attempt >= max_attempts - 1 or not _is_recoverable_sql_error(err_text):
                break
            sql = normalize_llm_sql(
                repair_sql(
                    active_question,
                    schema_context,
                    sql,
                    err_text,
                    model=model,
                    backend=backend,
                    base_url=base_url,
                    gap_instructions=gap_instructions,
                    rag_supplement=rag_supplement,
                    conversation_history=chat_history,
                    prior_result=prior,
                )
            )

    partial_note = "Showing a partial answer — some requested data was not available in the catalog."
    try:
        sql = normalize_llm_sql(
            generate_partial_sql(
                active_question,
                schema_context,
                failed_sql=sql,
                error_messages=errors,
                gap_instructions=gap_instructions,
                rag_supplement=rag_supplement,
                model=model,
                backend=backend,
                base_url=base_url,
            )
        )
        columns, rows = execute_readonly_sql(source_id, sql)
        if partial_note not in notes:
            notes.append(partial_note)
        return sql, columns, rows, notes
    except Exception as partial_exc:
        if last_exc:
            raise last_exc from partial_exc
        raise partial_exc


def execute_readonly_sql(source_id: str, sql: str, *, max_rows: int = 500) -> tuple[list[str], list[list[Any]]]:
    """
    Run validated read-only SQL against a structured dataset via Trino (or legacy direct Postgres).
    """
    validate_readonly_sql(sql)
    source = get_source(source_id=source_id)
    if not source or not is_structured_sql_connector(source.get("connector")):
        raise ValueError("Dataset is not a structured SQL connection")

    connector = (source.get("connector") or "").strip().lower()
    if connector == "trino":
        from structured_trino import execute_readonly_trino_sql, trino_config_from_source

        sql = prepare_sql_for_execution(sql, connector)
        return execute_readonly_trino_sql(trino_config_from_source(source), sql, max_rows=max_rows)

    import pg8000.native

    from structured_db import _connect_external

    cfg = postgres_config_from_source(source)
    limited = f"SELECT * FROM ({sql.rstrip(';')}) AS _q LIMIT {max_rows}"
    conn = _connect_external(cfg)
    try:
        result = conn.run(limited)
        columns = getattr(conn, "columns", None) or []
        col_names = [c["name"] if isinstance(c, dict) else str(c) for c in columns]
        if not result:
            return col_names, []
        rows = [list(r) for r in result]
        if not col_names and rows:
            col_names = [f"col_{i}" for i in range(len(rows[0]))]
        return col_names, coerce_json_rows(rows)
    finally:
        conn.close()


def plan_structured_query(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
    routing: dict[str, Any] | None = None,
    domain_id: str | None = None,
    source_id: str | None = None,
    table_names: list[str] | None = None,
    force_structured: bool = False,
) -> StructuredQueryPlan | None:
    """
    Route → pick dataset → build schema context.
    SQL generation is a separate LLM call (not implemented here).

    When the caller already routed the question (e.g. /api/ask), pass `routing`
    and `domain_id` to avoid a second embedding pass. Use `force_structured=True`
    when execution_kind is already sql/hybrid.
    """
    if routing is None:
        routing = route_question(question, embedder, domain_override=domain_override)
    domain_id = domain_id or routing.get("domain_id")
    if not domain_id:
        return None

    if not force_structured:
        mode = classify_retrieval_mode(question, domain_id=domain_id, routing=routing)
        if mode == "unstructured":
            return None

    dataset = None
    if source_id:
        dataset = get_source(source_id=source_id)
    if not dataset:
        dataset = pick_structured_dataset(question, domain_id, embedder)
    if not dataset:
        return None

    narrowed = table_names or (routing or {}).get("table_names")
    ctx = build_domain_schema_context(domain_id, dataset["id"], table_names=narrowed)
    return StructuredQueryPlan(
        question=question,
        domain_id=domain_id,
        source_id=dataset["id"],
        sql="",  # filled by LLM: generate_sql(question, ctx)
        schema_context=ctx,
        routing=routing,
    )


def query_structured_data(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
    generate_sql=None,
) -> StructuredQueryResult:
    """
    End-to-end structured path. Pass `generate_sql(question, ctx) -> str` from LLM layer.

    Not wired to /api/ask yet — call when Phase 2 is enabled.
    """
    plan = plan_structured_query(question, embedder, domain_override=domain_override)
    if not plan:
        raise ValueError("Question does not map to a structured dataset")

    if generate_sql is None:
        raise NotImplementedError(
            "SQL generation not configured. Provide generate_sql(question, schema_context) "
            "using your LLM service (Mistral/Bedrock/etc.)."
        )

    plan.sql = generate_sql(question, plan.schema_context)
    columns, rows = execute_readonly_sql(plan.source_id, plan.sql)

    summary_prompt = build_sql_summary_prompt(
        question=question,
        columns=columns,
        rows=rows,
    )
    return StructuredQueryResult(
        plan=plan,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        summary_prompt=summary_prompt,
    )
