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
from catalog_service import load_dataset_definition
from domain_router import route_question
from api.answer_format import build_sql_summary_prompt
from serde import coerce_json_rows
from structured_db import postgres_config_from_source

RetrievalMode = Literal["unstructured", "structured", "hybrid"]

_ANALYTICAL_PATTERNS = re.compile(
    r"\b(how many|count|total|sum|average|avg|min|max|list|show me|top \d+|"
    r"employees|revenue|sales|headcount|tenure|between|per month|per year|"
    r"group by|breakdown|trend)\b",
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
    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if source.get("connector") != "postgres":
            continue
        for table in list_table_metadata(source["id"]):
            if table_mentioned_in_question(table["table_name"], question):
                return True
    return False


def score_structured_domain_fit(question: str, domain_id: str, embedder=None) -> int:
    """Higher = better structured postgres match for this question in this domain."""
    if not should_use_structured_sql(question, domain_id):
        return 0
    dataset = pick_structured_dataset(question, domain_id, embedder)
    if not dataset:
        return 0

    score = 1
    q_lower = question.lower()
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2}
    dname = dataset.get("name", "").lower()
    for tok in q_tokens:
        if tok in dname:
            score += 3
    for table in list_table_metadata(dataset["id"]):
        tname = table["table_name"].lower()
        if tname in q_lower or tname.replace("_", " ") in q_lower:
            score += 5
        for part in tname.split("_"):
            if len(part) > 2 and part in q_tokens:
                score += 2
    return score


def find_best_structured_domain(
    question: str,
    embedder=None,
    *,
    prefer_domain_id: str | None = None,
    allowed_domain_ids: list[str] | None = None,
) -> dict | None:
    """Return the domain with the strongest structured postgres match for this question."""
    from catalog_db import get_domain
    from routing_cache import get_cached_routing_context

    q_tokens = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}

    def _score_domain(domain_id: str, boost: int = 0) -> int:
        return score_structured_domain_fit(question, domain_id, embedder) + boost

    # Fast path: keyword-routed domain with a strong table/name match.
    if prefer_domain_id:
        prefer_score = _score_domain(prefer_domain_id, boost=1)
        if prefer_score >= 5:
            domain = get_domain(domain_id=prefer_domain_id)
            return domain

    best: dict | None = None
    best_score = 0
    domains = get_cached_routing_context()
    if allowed_domain_ids:
        allowed = set(allowed_domain_ids)
        domains = [domain for domain in domains if domain["id"] in allowed]
    if not domains:
        return None
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
        score = _score_domain(domain["id"], boost=boost)
        if score > best_score:
            best_score = score
            best = domain
        if score >= 8 and domain["id"] == prefer_domain_id:
            break
    return best if best_score > 0 else None


def _tokenize_domain(domain: dict) -> set[str]:
    parts = [domain.get("name", ""), domain.get("description", ""), domain.get("slug", "")]
    for source in domain.get("sources") or []:
        parts.append(source.get("name", ""))
        for table_name in source.get("table_names") or []:
            parts.extend(table_name.replace("_", " ").split())
    return {t for t in re.findall(r"[a-z0-9]+", " ".join(parts).lower()) if len(t) > 2}


def should_use_structured_sql(question: str, domain_id: str | None) -> bool:
    """Route to SQL when analytics or catalog table names match the question."""
    if not domain_id:
        return False
    structured = list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
    if not structured:
        return False
    if _ANALYTICAL_PATTERNS.search(question):
        return True
    if question_references_catalog_tables(question, domain_id):
        return True
    if _DESCRIPTIVE_STRUCTURED_PATTERNS.search(question):
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}
        for source in structured:
            if source.get("connector") != "postgres":
                continue
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

    def cataloged_relations(self) -> list[str]:
        return [f"{t['table_schema']}.{t['table_name']}" for t in self.tables]

    def to_llm_prompt_block(self) -> str:
        relations = self.cataloged_relations()
        lines = [
            f"# Dataset: {self.source_name}",
            f"Domain: {self.domain_name}",
            f"Connector: {self.connector}",
            "",
            "## Allowed tables (use ONLY these exact names in FROM/JOIN)",
        ]
        if relations:
            for rel in relations:
                lines.append(f"- `{rel}`")
        else:
            lines.append("- (no tables cataloged — cannot generate SQL)")
        lines.extend(
            [
                "",
                "Do NOT invent table names (e.g. use `customer_profiles`, not `customers`).",
                "",
                "## Dataset definition",
                self.dataset_definition_md or "(none)",
                "",
                "## Tables (detail)",
            ]
        )
        for table in self.tables:
            lines.append(f"### {table['table_schema']}.{table['table_name']}")
            if table.get("definition"):
                lines.append(table["definition"])
            lines.append("Columns:")
            for col in table.get("columns") or []:
                labels = ", ".join(col.get("labels") or []) or "—"
                desc = col.get("description") or ""
                lines.append(
                    f"- `{col['column_name']}` ({col.get('data_type', '?')}) "
                    f"labels: [{labels}] {desc}".strip()
                )
            lines.append("")
        lines.append(
            "Rules: generate READ-ONLY SELECT only; every table reference must match an "
            "entry in Allowed tables exactly; use labeled columns per business meaning; "
            "limit rows unless user asks for full export."
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
) -> dict | None:
    """Choose the best postgres dataset in a domain by table/name relevance."""
    candidates = [
        s
        for s in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
        if s.get("connector") == "postgres"
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    q_lower = question.lower()
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 2}
    scored: list[tuple[int, dict]] = []
    for source in candidates:
        score = 0
        name = source.get("name", "").lower()
        if any(tok in name for tok in q_tokens):
            score += 2
        for table in list_table_metadata(source["id"]):
            tname = table["table_name"].lower()
            if tname in q_lower:
                score += 4
            for part in tname.split("_"):
                if len(part) > 2 and part in q_tokens:
                    score += 2
        scored.append((score, source))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored[0][0] > 0 else candidates[0]


def build_schema_context(source_id: str) -> StructuredSchemaContext:
    """Assemble catalog metadata for LLM SQL generation."""
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")

    columns_by_table = list_columns_by_source(source_id)
    tables_out: list[dict[str, Any]] = []
    for table in list_table_metadata(source_id):
        if not table.get("enabled", True):
            continue
        tables_out.append(
            {
                **table,
                "columns": columns_by_table.get(table["id"], []),
            }
        )

    return StructuredSchemaContext(
        source_id=source_id,
        source_name=source["name"],
        domain_id=source["domain_id"],
        domain_name=source.get("domain_name", ""),
        connector=source["connector"],
        dataset_definition_md=load_dataset_definition(source),
        tables=tables_out,
    )


def build_domain_schema_context(domain_id: str, primary_source_id: str) -> StructuredSchemaContext:
    """All cataloged postgres tables in a domain — for cross-dataset SQL (e.g. sales + countries)."""
    primary = get_source(source_id=primary_source_id)
    if not primary:
        raise ValueError(f"Dataset not found: {primary_source_id}")

    definition_parts: list[str] = []
    tables_out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for source in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True):
        if source.get("connector") != "postgres":
            continue
        def_md = load_dataset_definition(source)
        if def_md.strip():
            definition_parts.append(f"### {source['name']}\n{def_md}")
        columns_by_table = list_columns_by_source(source["id"])
        for table in list_table_metadata(source["id"]):
            if not table.get("enabled", True):
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
        connector="postgres",
        dataset_definition_md="\n\n".join(definition_parts),
        tables=tables_out,
    )


def validate_readonly_sql(sql: str) -> None:
    """Reject anything that is not a single read-only SELECT."""
    normalized = sql.strip().rstrip(";").lower()
    if not normalized.startswith("select"):
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
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Multiple statements are not allowed")


def _is_recoverable_sql_error(message: str) -> bool:
    lower = message.lower()
    return (
        "does not exist" in lower
        or "42p01" in lower
        or "undefined column" in lower
        or "42703" in lower
        or "ambiguous" in lower
    )


def generate_and_execute_readonly_sql(
    question: str,
    source_id: str,
    schema_context: StructuredSchemaContext,
    *,
    model: str,
    backend: str = "mistral",
    base_url: str = "http://localhost:11434",
    max_attempts: int = 2,
) -> tuple[str, list[str], list[list[Any]], list[str]]:
    """Generate SQL from catalog schema, execute, retry on errors, then partial fallback."""
    from api.llm import generate_partial_sql, generate_sql, repair_sql
    from api.schema_gaps import analyze_schema_gaps, note_from_sql_error

    if not schema_context.tables:
        raise ValueError(
            "No tables are cataloged for this dataset. Open Data Catalog → dataset → "
            "Data tab → discover and add tables before running analytics."
        )

    gap_analysis = analyze_schema_gaps(question, schema_context)
    notes: list[str] = list(gap_analysis.notes)
    gap_instructions = gap_analysis.skip_instructions
    errors: list[str] = []

    sql = generate_sql(
        question,
        schema_context,
        model=model,
        backend=backend,
        base_url=base_url,
        gap_instructions=gap_instructions,
    )
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
            sql = repair_sql(
                question,
                schema_context,
                sql,
                err_text,
                model=model,
                backend=backend,
                base_url=base_url,
                gap_instructions=gap_instructions,
            )

    partial_note = "Showing a partial answer — some requested data was not available in the catalog."
    try:
        sql = generate_partial_sql(
            question,
            schema_context,
            failed_sql=sql,
            error_messages=errors,
            gap_instructions=gap_instructions,
            model=model,
            backend=backend,
            base_url=base_url,
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
    Run validated read-only SQL against a cataloged postgres dataset.
  Uses the dataset's stored connection config (read-only DB user in production).
    """
    validate_readonly_sql(sql)
    source = get_source(source_id=source_id)
    if not source or source.get("connector") != "postgres":
        raise ValueError("Dataset is not a postgres connection")

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

    dataset = pick_structured_dataset(question, domain_id, embedder)
    if not dataset:
        return None

    ctx = build_domain_schema_context(domain_id, dataset["id"])
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
