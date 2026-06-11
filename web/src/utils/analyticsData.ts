export type ChartType = "bar" | "line" | "pie";

export function humanizeColumn(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value);
}

function isNumericValue(value: unknown): boolean {
  if (value == null || value === "") return false;
  if (typeof value === "number" && !Number.isNaN(value)) return true;
  const n = Number(value);
  return !Number.isNaN(n) && String(value).trim() !== "";
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
): { labels: string[]; values: number[]; valueLabel: string } {
  const slice = rows.slice(0, maxPoints);
  const labels: string[] = [];
  const values: number[] = [];
  for (const row of slice) {
    const rawLabel = labelIdx < row.length ? row[labelIdx] : "";
    labels.push(rawLabel == null || rawLabel === "" ? "—" : String(rawLabel));
    const rawVal = valueIdx < row.length ? row[valueIdx] : 0;
    const n = typeof rawVal === "number" ? rawVal : Number(rawVal);
    values.push(Number.isNaN(n) ? 0 : n);
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
