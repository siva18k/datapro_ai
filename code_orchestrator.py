"""
LLM-generated Python for data curation (Phase 2+).

When data is too large or too raw for vector RAG alone, the LLM writes Python to:
  - read CSV / Excel / JSON / text files from a cataloged dataset folder
  - filter, join, aggregate, sample
  - produce a small curated payload for the final answer LLM

Execution must run in an isolated sandbox (ECS Fargate task, Lambda, or gVisor).
Local dev can use execute_python_curation_local() with strict guards only.

Typical pipeline:

  route domain → pick dataset (upload / file_path / postgres+export)
  → build execution context (paths, definitions, labels)
  → LLM generates SQL *or* Python
  → sandbox executes
  → curated result (≤ N rows / tokens) → answer LLM
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from catalog_db import get_source, list_sources
from catalog_service import get_source_data_path, list_source_files, load_dataset_definition
from domain_router import route_question
from structured_orchestrator import _ANALYTICAL_PATTERNS, should_use_structured_sql

ExecutionKind = Literal["sql", "python", "rag", "hybrid"]

_FORBIDDEN_PYTHON = re.compile(
    r"\b(import os|import sys|import subprocess|import shutil|import socket|"
    r"from os |from sys |open\s*\(|exec\s*\(|eval\s*\(|__import__|"
    r"compile\s*\(|globals\s*\(|locals\s*\(|getattr\s*\(|setattr\s*\()\b",
    re.I,
)

_CURATION_PATTERNS = re.compile(
    r"\b(csv|spreadsheet|excel|aggregate|filter|pivot|group by|sum of|total of|"
    r"combine|merge|join|clean|curate|large file|all records|every row|"
    r"export|calculate from file)\b",
    re.I,
)

# Libraries allowed in sandbox (expand via ECS image)
ALLOWED_PYTHON_IMPORTS = frozenset({"pandas", "pd", "json", "math", "datetime", "re", "csv"})


@dataclass
class CuratedPayload:
    """Small result passed to the answer LLM after code/SQL runs."""

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    summary_stats: dict[str, Any] = field(default_factory=dict)
    narrative: str = ""
    row_count: int = 0
    truncated: bool = False

    def to_answer_context(self, max_rows: int = 50) -> str:
        sample = self.rows[:max_rows]
        return json.dumps(
            {
                "columns": self.columns,
                "rows": sample,
                "row_count": self.row_count,
                "truncated": self.truncated or len(self.rows) > max_rows,
                "summary_stats": self.summary_stats,
                "narrative": self.narrative,
            },
            default=str,
        )


@dataclass
class FileDatasetContext:
    """Grounding for Python that reads files in a dataset directory."""

    source_id: str
    source_name: str
    domain_id: str
    domain_name: str
    connector: str
    data_dir: str
    dataset_definition_md: str
    files: list[dict[str, Any]] = field(default_factory=list)

    def to_llm_prompt_block(self) -> str:
        lines = [
            f"# Dataset: {self.source_name}",
            f"Domain: {self.domain_name}",
            f"Data directory (read-only): `{self.data_dir}`",
            "",
            "## Dataset definition",
            self.dataset_definition_md or "(none)",
            "",
            "## Files",
        ]
        for f in self.files:
            lines.append(f"- `{f['name']}` ({f['size_bytes']} bytes, {f['extension']})")
        lines.extend(
            [
                "",
                "## Python curation rules",
                "- Use only: pandas, json, csv, datetime, math, re",
                "- Read files only under the data directory path above",
                "- Do not access network, subprocess, or filesystem outside data_dir",
                "- Filter/aggregate to answer the user question",
                "- Assign final output to variable `result` as a dict:",
                '  result = {"columns": [...], "rows": [[...]], "summary_stats": {}, "narrative": "..."}',
                "- Keep rows ≤ 500 unless user explicitly needs more",
            ]
        )
        return "\n".join(lines)


@dataclass
class CodeExecutionPlan:
    question: str
    domain_id: str | None
    source_id: str
    kind: ExecutionKind
    routing: dict[str, Any]
    context_prompt: str
    code: str = ""


def classify_execution_kind(
    question: str,
    *,
    domain_id: str | None,
    routing: dict[str, Any] | None = None,
) -> ExecutionKind:
    """
    Choose rag vs sql vs python vs hybrid.
    Replace with LLM router when ready.
    """
    if not domain_id:
        return "rag"

    structured = list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
    file_sources = [
        s
        for s in list_sources(domain_id=domain_id, source_type="unstructured", enabled_only=True)
        if s.get("connector") in ("upload", "file_path")
    ]

    wants_analytics = bool(_ANALYTICAL_PATTERNS.search(question))
    wants_curation = bool(_CURATION_PATTERNS.search(question))
    wants_structured = should_use_structured_sql(question, domain_id)

    if structured and (wants_analytics or wants_structured):
        if file_sources and wants_curation:
            return "hybrid"
        return "sql"
    if file_sources and (wants_curation or wants_analytics):
        return "python"
    return "rag"


def pick_file_dataset(question: str, domain_id: str, embedder=None) -> dict | None:
    candidates = [
        s
        for s in list_sources(domain_id=domain_id, enabled_only=True)
        if s.get("connector") in ("upload", "file_path")
    ]
    if not candidates:
        return None
    # Future: rank by file names / definition relevance
    return candidates[0]


def build_file_dataset_context(source_id: str) -> FileDatasetContext:
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")

    data_path = get_source_data_path(source)
    files_meta: list[dict[str, Any]] = []
    for fp in list_source_files(source):
        files_meta.append(
            {
                "name": fp.name,
                "path": str(fp),
                "size_bytes": fp.stat().st_size,
                "extension": fp.suffix.lower(),
            }
        )

    return FileDatasetContext(
        source_id=source_id,
        source_name=source["name"],
        domain_id=source["domain_id"],
        domain_name=source.get("domain_name", ""),
        connector=source["connector"],
        data_dir=str(data_path),
        dataset_definition_md=load_dataset_definition(source),
        files=files_meta,
    )


def validate_python_curation_code(code: str) -> None:
    """Static checks before sandbox execution."""
    if _FORBIDDEN_PYTHON.search(code):
        raise ValueError("Code contains forbidden operations (os, subprocess, open, exec, etc.)")
    if len(code) > 20_000:
        raise ValueError("Code exceeds maximum length")


def execute_python_curation_local(
    source_id: str,
    code: str,
    *,
    max_rows: int = 500,
) -> CuratedPayload:
    """
    DEV ONLY — runs curated Python in-process with a minimal namespace.
    Production must use execute_python_curation_sandbox() on ECS/Lambda.
    """
    validate_python_curation_code(code)
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError("Dataset not found")

    data_dir = get_source_data_path(source)
    namespace: dict[str, Any] = {
        "DATA_DIR": str(data_dir),
        "data_dir": str(data_dir),
        "Path": Path,
        "result": None,
    }

    try:
        import pandas as pd  # noqa: F401

        namespace["pd"] = pd
        namespace["pandas"] = pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for Python curation") from exc

    namespace["json"] = json
    exec(code, {"__builtins__": _safe_builtins()}, namespace)  # noqa: S102

    raw = namespace.get("result")
    if not isinstance(raw, dict):
        raise ValueError("Code must assign `result` dict with columns and rows")

    rows = raw.get("rows") or []
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]

    return CuratedPayload(
        columns=list(raw.get("columns") or []),
        rows=[list(r) for r in rows],
        summary_stats=dict(raw.get("summary_stats") or {}),
        narrative=str(raw.get("narrative") or ""),
        row_count=len(rows),
        truncated=truncated,
    )


def _safe_builtins() -> dict[str, Any]:
    import builtins

    allowed = (
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "int",
        "float",
        "str",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "isinstance",
        "print",
        "any",
        "all",
    )
    return {k: getattr(builtins, k) for k in allowed if hasattr(builtins, k)}


def execute_python_curation_sandbox(
    source_id: str,
    code: str,
    *,
    max_rows: int = 500,
) -> CuratedPayload:
    """
    Production entrypoint — dispatch to isolated worker (ECS task / Lambda).

    Not implemented: wire when containerizing. Env vars:
      SANDBOX_TASK_DEFINITION, DATASET_MOUNT_PATH, EXECUTION_TIMEOUT_SEC
    """
    raise NotImplementedError(
        "Sandbox execution is not configured. On AWS ECS, run Python in a "
        "dedicated Fargate task with read-only volume mount for the dataset path."
    )


def plan_code_curation(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
) -> CodeExecutionPlan | None:
    routing = route_question(question, embedder, domain_override=domain_override)
    domain_id = routing.get("domain_id")
    if not domain_id:
        return None

    kind = classify_execution_kind(question, domain_id=domain_id, routing=routing)
    if kind == "rag":
        return None

    if kind == "sql":
        from structured_orchestrator import plan_structured_query

        sql_plan = plan_structured_query(question, embedder, domain_override=domain_override)
        if not sql_plan:
            return None
        return CodeExecutionPlan(
            question=question,
            domain_id=domain_id,
            source_id=sql_plan.source_id,
            kind="sql",
            routing=routing,
            context_prompt=sql_plan.schema_context.to_llm_prompt_block(),
        )

    dataset = pick_file_dataset(question, domain_id, embedder)
    if not dataset:
        return None

    ctx = build_file_dataset_context(dataset["id"])
    return CodeExecutionPlan(
        question=question,
        domain_id=domain_id,
        source_id=dataset["id"],
        kind=kind,
        routing=routing,
        context_prompt=ctx.to_llm_prompt_block(),
    )


def curate_data_for_question(
    question: str,
    embedder=None,
    *,
    domain_override: str | None = None,
    generate_code=None,
    use_sandbox: bool = False,
) -> tuple[CuratedPayload, CodeExecutionPlan]:
    """
    End-to-end curation. Pass generate_code(question, context_prompt, kind) -> str.

    For SQL kind, generate_code should return SQL string; execution uses structured_orchestrator.
    For python kind, generate_code returns Python assigning `result`.
    """
    plan = plan_code_curation(question, embedder, domain_override=domain_override)
    if not plan:
        raise ValueError("No curation plan for this question")

    if generate_code is None:
        raise NotImplementedError("Provide generate_code from your LLM service")

    plan.code = generate_code(question, plan.context_prompt, plan.kind)

    if plan.kind == "sql":
        from structured_orchestrator import execute_readonly_sql

        cols, rows = execute_readonly_sql(plan.source_id, plan.code)
        payload = CuratedPayload(
            columns=cols,
            rows=rows,
            row_count=len(rows),
            truncated=len(rows) >= 500,
        )
        return payload, plan

    executor = execute_python_curation_sandbox if use_sandbox else execute_python_curation_local
    payload = executor(plan.source_id, plan.code)
    return payload, plan
