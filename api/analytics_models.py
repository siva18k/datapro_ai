from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalyticsRequest(BaseModel):
    prompt: str
    domain_override: str | None = None
    domain_overrides: list[str] | None = None
    backend: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None


class KpiWidget(BaseModel):
    type: Literal["kpi"] = "kpi"
    label: str
    value: str
    hint: str | None = None


class AnalyticsChartDefaults(BaseModel):
    chart_type: Literal["bar", "line", "pie"] = "bar"
    label_column: int = 0
    value_column: int = 0
    chart_title: str | None = None


class AnalyticsResponse(BaseModel):
    title: str
    summary: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    total_rows: int | None = None
    chart_defaults: AnalyticsChartDefaults | None = None
    kpis: list[KpiWidget] = Field(default_factory=list)
    domain_name: str | None = None
    routing_method: str | None = None
    query_kind: str | None = None
    sql: str | None = None
    notes: list[str] = Field(default_factory=list)
