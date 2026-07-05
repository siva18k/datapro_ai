"""Infer referential relationships between cataloged tables for dataset definitions."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from catalog_db import get_source, list_columns_by_source, list_table_metadata
from structured_sql import is_structured_sql_connector

RELATIONSHIPS_START = "<!-- datapro:relationships:start -->"
RELATIONSHIPS_END = "<!-- datapro:relationships:end -->"
_RELATIONSHIPS_PATTERN = re.compile(
    re.escape(RELATIONSHIPS_START) + r".*?" + re.escape(RELATIONSHIPS_END),
    re.DOTALL,
)

_ROLE_LABELS = {
    "fact": "fact / dimension",
    "lookup": "lookup",
    "excluded": "excluded",
}


@dataclass(frozen=True)
class InferredRelationship:
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    source: str
    confidence: str
    note: str

    def from_qualified(self) -> str:
        return f"{self.from_schema}.{self.from_table}"

    def to_qualified(self) -> str:
        return f"{self.to_schema}.{self.to_table}"

    def key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.from_schema,
            self.from_table,
            self.from_column,
            self.to_schema,
            self.to_table,
            self.to_column,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "from_table": self.from_qualified(),
            "from_column": self.from_column,
            "to_table": self.to_qualified(),
            "to_column": self.to_column,
            "source": self.source,
            "confidence": self.confidence,
            "note": self.note,
        }


def _singularize(name: str) -> str:
    if name.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if name.endswith("s") and not name.endswith("ss") and len(name) > 1:
        return name[:-1]
    return name


def _pluralize(name: str) -> str:
    if name.endswith("y") and len(name) > 1:
        return name[:-1] + "ies"
    if name.endswith("s"):
        return name
    return name + "s"


def _strip_table_prefix(name: str) -> str:
    for prefix in ("reference_", "dim_", "fact_", "lookup_", "ref_"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _table_name_variants(table_name: str) -> set[str]:
    bare = _strip_table_prefix(table_name)
    return {
        table_name,
        bare,
        _singularize(bare),
        _pluralize(bare),
        _singularize(table_name),
        _pluralize(table_name),
    }


def _qualified(schema: str, table: str) -> str:
    return f"{schema}.{table}"


def _type_family(data_type: str) -> str:
    dt = (data_type or "").lower()
    if any(token in dt for token in ("uuid",)):
        return "uuid"
    if any(token in dt for token in ("int", "serial", "bigint", "smallint")):
        return "int"
    if any(token in dt for token in ("char", "text", "varchar")):
        return "text"
    return dt or "unknown"


def _types_compatible(left: str, right: str) -> bool:
    left_f = _type_family(left)
    right_f = _type_family(right)
    if left_f == "unknown" or right_f == "unknown":
        return True
    if left_f == right_f:
        return True
    if {left_f, right_f} <= {"int", "uuid"}:
        return False
    return left_f == right_f


def _score_table_match(column_base: str, table_name: str) -> int:
    variants = _table_name_variants(table_name)
    bases = {column_base, _singularize(column_base), _pluralize(column_base)}
    if bases & variants:
        return 100
    bare = _strip_table_prefix(table_name)
    bare_names = {bare, _singularize(bare), _pluralize(bare)}
    if bases & bare_names:
        return 95
    # Simple keys (customer_id → customers) must match the entity name exactly.
    if "_" not in column_base:
        return 0
    for base in bases:
        for candidate in bare_names:
            if candidate.startswith(f"{base}_") or candidate == _pluralize(base):
                return 85
    return 0


def _pick_target_column(
    fk_column: str,
    target_columns: list[dict[str, Any]],
    *,
    prefer_lookup: bool,
) -> dict[str, Any] | None:
    if not target_columns:
        return None
    by_name = {c["column_name"]: c for c in target_columns}
    if fk_column in by_name:
        return by_name[fk_column]
    for candidate in ("id", f"{fk_column}"):
        if candidate in by_name:
            return by_name[candidate]
    for col in target_columns:
        if col["column_name"] == "id":
            return col
    if prefer_lookup:
        for col in target_columns:
            if col["column_name"].endswith("_id"):
                return col
    return target_columns[0]


def _is_bridge_table(table_name: str) -> bool:
    return table_name.endswith("_bridge") or table_name.endswith("_bridges")


def _relationship_note(
    *,
    from_column: str,
    from_table: dict[str, Any],
    to_table: dict[str, Any],
    source: str,
) -> str:
    to_role = to_table.get("table_role") or "fact"
    from_name = from_table["table_name"]
    to_name = to_table["table_name"]
    to_qualified = f"{to_table['table_schema']}.{to_name}"

    if _is_bridge_table(from_name):
        if from_column == "segment_id" or "segment" in from_column:
            return (
                f"Bridge table — join `{from_name}` to `{to_qualified}` on `{from_column}` "
                f"for segment names/details (customers link to segments through this table)."
            )
        return (
            f"Bridge table — use `{from_name}` to link `{from_name.split('_bridge')[0]}` "
            f"entities via `{from_column}` → `{to_qualified}`."
        )

    if source == "database":
        if from_column.endswith("_id"):
            return (
                f"Foreign key — join `{from_table['table_schema']}.{from_name}.{from_column}` "
                f"to `{to_qualified}.{from_column}`."
            )
        return (
            f"Foreign key — join `{from_table['table_schema']}.{from_name}.{from_column}` "
            f"to `{to_qualified}`."
        )

    to_label = _ROLE_LABELS.get(to_role, to_role)
    if to_role == "lookup":
        return (
            f"Join `{from_column}` to `{to_qualified}` ({to_label}) "
            f"for descriptive attributes (names, codes, labels)."
        )
    return (
        f"Join `{from_table['table_schema']}.{from_name}.{from_column}` "
        f"to `{to_qualified}` for related rows."
    )


def _load_catalog_tables(source_id: str) -> list[dict[str, Any]]:
    columns_by_table = list_columns_by_source(source_id)
    tables: list[dict[str, Any]] = []
    for table in list_table_metadata(source_id):
        if not table.get("enabled", True):
            continue
        role = table.get("table_role") or "fact"
        if role == "excluded":
            continue
        tables.append({**table, "columns": columns_by_table.get(table["id"], [])})
    return tables


def _infer_from_database_fks(
    source: dict[str, Any],
    tables: list[dict[str, Any]],
) -> list[InferredRelationship]:
    if source.get("connector") not in ("postgres", "trino"):
        return []
    catalog_keys = {(t["table_schema"], t["table_name"]) for t in tables}
    table_by_key = {(t["table_schema"], t["table_name"]): t for t in tables}
    try:
        from structured_db import list_foreign_keys_for_source

        fks = list_foreign_keys_for_source(source)
    except Exception:
        return []

    relationships: list[InferredRelationship] = []
    for fk in fks:
        from_key = (fk["table_schema"], fk["table_name"])
        to_key = (fk["foreign_table_schema"], fk["foreign_table_name"])
        if from_key not in catalog_keys or to_key not in catalog_keys:
            continue
        from_table = table_by_key[from_key]
        to_table = table_by_key[to_key]
        relationships.append(
            InferredRelationship(
                from_schema=fk["table_schema"],
                from_table=fk["table_name"],
                from_column=fk["column_name"],
                to_schema=fk["foreign_table_schema"],
                to_table=fk["foreign_table_name"],
                to_column=fk["foreign_column_name"],
                source="database",
                confidence="high",
                note=_relationship_note(
                    from_column=fk["column_name"],
                    from_table=from_table,
                    to_table=to_table,
                    source="database",
                ),
            )
        )
    return relationships


def _infer_from_column_naming(tables: list[dict[str, Any]]) -> list[InferredRelationship]:
    relationships: list[InferredRelationship] = []
    for from_table in tables:
        from_role = from_table.get("table_role") or "fact"
        if from_role == "excluded":
            continue
        for col in from_table.get("columns") or []:
            column_name = col["column_name"]
            if column_name == "id" or not column_name.endswith("_id"):
                continue
            column_base = column_name[: -len("_id")]
            if not column_base:
                continue

            best_target: dict[str, Any] | None = None
            best_score = 0
            best_target_col: dict[str, Any] | None = None
            for candidate in tables:
                if candidate["id"] == from_table["id"]:
                    continue
                score = _score_table_match(column_base, candidate["table_name"])
                if candidate.get("table_role") == "lookup":
                    score += 15
                if score < 70:
                    continue
                target_col = _pick_target_column(
                    column_name,
                    candidate.get("columns") or [],
                    prefer_lookup=candidate.get("table_role") == "lookup",
                )
                if not target_col:
                    continue
                if not _types_compatible(col.get("data_type", ""), target_col.get("data_type", "")):
                    score -= 25
                if score > best_score:
                    best_score = score
                    best_target = candidate
                    best_target_col = target_col

            if not best_target or not best_target_col or best_score < 70:
                continue

            relationships.append(
                InferredRelationship(
                    from_schema=from_table["table_schema"],
                    from_table=from_table["table_name"],
                    from_column=column_name,
                    to_schema=best_target["table_schema"],
                    to_table=best_target["table_name"],
                    to_column=best_target_col["column_name"],
                    source="naming",
                    confidence="medium" if best_score < 95 else "high",
                    note=_relationship_note(
                        from_column=column_name,
                        from_table=from_table,
                        to_table=best_target,
                        source="naming",
                    ),
                )
            )
    return relationships


def _infer_from_column_labels(tables: list[dict[str, Any]]) -> list[InferredRelationship]:
    relationships: list[InferredRelationship] = []
    lookup_tables = [t for t in tables if (t.get("table_role") or "fact") == "lookup"]
    if not lookup_tables:
        return relationships

    for from_table in tables:
        for col in from_table.get("columns") or []:
            labels = [label.strip().lower() for label in (col.get("labels") or []) if label.strip()]
            if not labels:
                continue
            for label in labels:
                label_key = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
                if not label_key:
                    continue
                for target in lookup_tables:
                    if target["id"] == from_table["id"]:
                        continue
                    score = _score_table_match(label_key, target["table_name"])
                    if score < 80:
                        continue
                    target_col = _pick_target_column(
                        col["column_name"],
                        target.get("columns") or [],
                        prefer_lookup=True,
                    )
                    if not target_col:
                        continue
                    relationships.append(
                        InferredRelationship(
                            from_schema=from_table["table_schema"],
                            from_table=from_table["table_name"],
                            from_column=col["column_name"],
                            to_schema=target["table_schema"],
                            to_table=target["table_name"],
                            to_column=target_col["column_name"],
                            source="labels",
                            confidence="medium",
                            note=(
                                f"Column label «{label}» matches lookup table `{target['table_name']}` — "
                                f"use `{col['column_name']}` for segment/detail lookups."
                            ),
                        )
                    )
    return relationships


def _merge_relationships(*groups: list[InferredRelationship]) -> list[InferredRelationship]:
    priority = {"database": 3, "naming": 2, "labels": 1}
    merged: dict[tuple[str, str, str, str, str, str], InferredRelationship] = {}
    for group in groups:
        for rel in group:
            existing = merged.get(rel.key())
            if existing is None or priority[rel.source] > priority[existing.source]:
                merged[rel.key()] = rel
    return sorted(
        merged.values(),
        key=lambda r: (r.from_qualified(), r.from_column, r.to_qualified(), r.to_column),
    )


def infer_relationships_for_source(source_id: str) -> list[dict[str, str]]:
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")
    tables = _load_catalog_tables(source_id)
    if len(tables) < 2:
        return []

    db_rels = _infer_from_database_fks(source, tables)
    # Prefer database FKs — naming heuristics only fill gaps.
    naming_rels = _infer_from_column_naming(tables)
    label_rels = _infer_from_column_labels(tables)
    return [rel.to_dict() for rel in _merge_relationships(db_rels, naming_rels, label_rels)]


def strip_relationships_section(definition_md: str) -> str:
    """Return definition markdown without the auto-generated relationships block."""
    return _RELATIONSHIPS_PATTERN.sub("", definition_md).strip()


def format_relationships_markdown(
    relationships: list[dict[str, str]],
    *,
    tables: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "## Table relationships (auto-generated)",
        "",
        "Join paths between cataloged tables (from database foreign keys and column naming). "
        "Use schema-qualified names in SQL. Refresh after catalog changes.",
        "",
    ]
    if not relationships:
        lines.extend(
            [
                "_No relationships inferred yet. Catalog at least two tables with foreign keys "
                "or matching `*_id` columns, then refresh._",
                "",
            ]
        )
        return "\n".join(lines)

    target_counts = Counter(rel["to_table"] for rel in relationships)
    hub_tables = [name for name, count in target_counts.items() if count >= 2]
    bridge_tables = []
    if tables:
        bridge_tables = [
            f"{t['table_schema']}.{t['table_name']}"
            for t in tables
            if _is_bridge_table(t["table_name"])
        ]

    if hub_tables:
        lines.extend(["### Hub tables", ""])
        for hub in sorted(hub_tables):
            count = target_counts[hub]
            lines.append(
                f"- **`{hub}`** — referenced by {count} join path(s); use as the central join target."
            )
        lines.append("")

    if bridge_tables:
        lines.extend(
            [
                "### Bridge tables",
                "",
                "Many-to-many or assignment tables — join through these instead of assuming FK columns on fact tables:",
                "",
            ]
        )
        for name in bridge_tables:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.extend(
        [
            "| From table | Column | To table | Column | Source |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for rel in relationships:
        lines.append(
            f"| `{rel['from_table']}` | `{rel['from_column']}` | "
            f"`{rel['to_table']}` | `{rel['to_column']}` | {rel['source']} |"
        )

    lines.extend(["", "### Join notes", ""])
    for rel in relationships:
        lines.append(
            f"- **{rel['from_table']}.{rel['from_column']}** → "
            f"**{rel['to_table']}.{rel['to_column']}** — {rel['note']}"
        )

    if tables:
        by_role: dict[str, list[str]] = {}
        for t in tables:
            role = t.get("table_role") or "fact"
            by_role.setdefault(role, []).append(f"`{t['table_schema']}.{t['table_name']}`")
        if by_role:
            lines.extend(["", "### Cataloged tables by role", ""])
            for role in ("fact", "lookup", "excluded"):
                names = by_role.get(role)
                if names:
                    label = _ROLE_LABELS.get(role, role)
                    lines.append(f"**{label}**: {', '.join(sorted(names))}")

    lines.append("")
    return "\n".join(lines)


def merge_relationships_into_definition(definition_md: str, section_md: str) -> str:
    block = f"{RELATIONSHIPS_START}\n{section_md.strip()}\n{RELATIONSHIPS_END}"
    if _RELATIONSHIPS_PATTERN.search(definition_md):
        return _RELATIONSHIPS_PATTERN.sub(block, definition_md).rstrip() + "\n"
    trimmed = definition_md.rstrip()
    if trimmed:
        return f"{trimmed}\n\n{block}\n"
    return f"{block}\n"


def build_relationships_section(source_id: str) -> dict[str, Any]:
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")
    tables = _load_catalog_tables(source_id)
    relationships = infer_relationships_for_source(source_id)
    markdown_section = format_relationships_markdown(relationships, tables=tables)
    return {
        "relationships": relationships,
        "markdown_section": markdown_section,
        "table_count": len(tables),
    }
