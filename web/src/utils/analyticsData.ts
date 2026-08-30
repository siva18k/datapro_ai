import type { TimeContext } from "../types";

export type ChartType = "bar" | "line" | "pie";

export function humanizeColumn(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function parseTemporalBucket(value: unknown): Date | null {
  if (value == null || value === "") return null;
  const text = String(value).trim();
  if (!text) return null;
  const parsed = Date.parse(text.replace(/Z$/, "Z"));
  if (Number.isNaN(parsed)) return null;
  return new Date(parsed);
}

function displayLabelForBucket(value: unknown, timeContext: TimeContext | undefined): string | null {
  if (!timeContext?.periods?.length) return null;
  const bucket = parseTemporalBucket(value);
  if (!bucket) return null;
  const bucketTime = bucket.getTime();
  for (const period of timeContext.periods) {
    const start = Date.parse(`${period.start}T00:00:00`);
    const end = Date.parse(`${period.end_exclusive}T00:00:00`);
    if (!Number.isNaN(start) && !Number.isNaN(end) && bucketTime >= start && bucketTime < end) {
      return period.label;
    }
  }
  return null;
}

export function formatCell(value: unknown, timeContext?: TimeContext): string {
  if (value == null) return "—";
  const periodLabel = displayLabelForBucket(value, timeContext);
  if (periodLabel) return periodLabel;
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function parseNumericValue(value: unknown): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  const text = String(value).trim().replace(/[$,\s]/g, "");
  if (!text || text === "-" || text === "—") return null;
  const n = Number(text);
  return Number.isNaN(n) ? null : n;
}

function isNumericValue(value: unknown): boolean {
  return parseNumericValue(value) != null;
}

export function numericColumnIndices(columns: string[], rows: unknown[][]): number[] {
  const indices: number[] = [];
  for (let ci = 0; ci < columns.length; ci += 1) {
    let hits = 0;
    let checked = 0;
    for (const row of rows.slice(0, 30)) {
      if (ci >= row.length) continue;
      checked += 1;
      if (isNumericValue(row[ci])) hits += 1;
    }
    if (checked > 0 && hits / checked >= 0.6) indices.push(ci);
  }
  return indices;
}

const LABEL_HINTS = /^(name|country|region|category|product|customer|month|year|date|label|title|id)$/i;
const VALUE_HINTS = /^(total|sum|count|amount|revenue|sales|qty|quantity|value|price|profit|cost)$/i;

export function defaultLabelColumn(columns: string[], numeric: Set<number>): number {
  for (let i = 0; i < columns.length; i += 1) {
    const base = columns[i].split(".").pop() ?? columns[i];
    if (!numeric.has(i) && LABEL_HINTS.test(base)) return i;
  }
  for (let i = 0; i < columns.length; i += 1) {
    if (!numeric.has(i)) return i;
  }
  return 0;
}

export function defaultValueColumn(columns: string[], numeric: number[]): number {
  for (const idx of numeric) {
    const base = columns[idx].split(".").pop() ?? columns[idx];
    if (VALUE_HINTS.test(base)) return idx;
  }
  return numeric[0] ?? 0;
}

export function buildChartSeries(
  columns: string[],
  rows: unknown[][],
  labelIdx: number,
  valueIdx: number,
  maxPoints = 50,
  timeContext?: TimeContext,
): { labels: string[]; values: number[]; valueLabel: string } {
  const slice = rows.slice(0, maxPoints);
  const labels: string[] = [];
  const values: number[] = [];
  for (const row of slice) {
    const rawLabel = labelIdx < row.length ? row[labelIdx] : "";
    const periodLabel = displayLabelForBucket(rawLabel, timeContext);
    labels.push(
      periodLabel ??
        (rawLabel == null || rawLabel === "" ? "—" : String(rawLabel)),
    );
    const rawVal = valueIdx < row.length ? row[valueIdx] : 0;
    const n = parseNumericValue(rawVal);
    values.push(n ?? 0);
  }
  return {
    labels,
    values,
    valueLabel: humanizeColumn(columns[valueIdx] ?? "Value"),
  };
}

export function canChart(columns: string[] | undefined, rows: unknown[][] | undefined): boolean {
  if (!columns?.length || !rows?.length || rows.length < 2) return false;
  return numericColumnIndices(columns, rows).length > 0;
}
