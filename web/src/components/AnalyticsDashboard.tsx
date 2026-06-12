import { useEffect, useMemo, useState } from "react";
import type { AnalyticsResponse } from "../types";
import {
  buildChartSeries,
  canChart,
  defaultLabelColumn,
  defaultValueColumn,
  formatCell,
  humanizeColumn,
  numericColumnIndices,
  type ChartType,
} from "../utils/analyticsData";
import { AnalyticsChart } from "./AnalyticsChart";
import { AnalyticsViewControls, type ViewVisibility } from "./AnalyticsViewControls";

interface Props {
  data: AnalyticsResponse | null;
  isRunning?: boolean;
  activityStatus?: string | null;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
}

function AnalyticsLoadingDots() {
  return (
    <div className="analytics-loading-dots" aria-hidden>
      <span className="analytics-loading-dot analytics-loading-dot--1" />
      <span className="analytics-loading-dot analytics-loading-dot--2" />
      <span className="analytics-loading-dot analytics-loading-dot--3" />
      <span className="analytics-loading-dot analytics-loading-dot--4" />
      <span className="analytics-loading-dot analytics-loading-dot--5" />
    </div>
  );
}

export function AnalyticsDashboard({
  data,
  isRunning,
  activityStatus,
  isFullscreen,
  onToggleFullscreen,
}: Props) {
  const [visibility, setVisibility] = useState<ViewVisibility>({
    summary: true,
    kpi: true,
    chart: true,
    table: true,
  });
  const [chartType, setChartType] = useState<ChartType>("bar");
  const [labelColumn, setLabelColumn] = useState(0);
  const [valueColumn, setValueColumn] = useState(0);

  const columns = data?.columns ?? [];
  const rows = data?.rows ?? [];
  const numericCols = useMemo(
    () => (columns.length && rows.length ? numericColumnIndices(columns, rows) : []),
    [columns, rows],
  );

  const chartAvailable = canChart(columns, rows);
  const kpiAvailable = (data?.kpis?.length ?? 0) > 0;
  const tableAvailable = columns.length > 0 && rows.length > 0;
  const summaryAvailable = Boolean(data?.summary?.trim());
  const notesAvailable = (data?.notes?.length ?? 0) > 0;

  useEffect(() => {
    if (!data) return;
    const defs = data.chart_defaults;
    setChartType(defs?.chart_type ?? "bar");
    if (columns.length && rows.length) {
      const numeric = numericColumnIndices(columns, rows);
      const numSet = new Set(numeric);
      setLabelColumn(defs?.label_column ?? defaultLabelColumn(columns, numSet));
      setValueColumn(defs?.value_column ?? defaultValueColumn(columns, numeric));
    }
    setVisibility({
      summary: Boolean(data.summary?.trim()),
      kpi: (data.kpis?.length ?? 0) > 0,
      chart: canChart(data.columns, data.rows),
      table: Boolean(data.columns?.length && data.rows?.length),
    });
  }, [data]);

  const chartSeries = useMemo(() => {
    if (!chartAvailable) return null;
    return buildChartSeries(columns, rows, labelColumn, valueColumn);
  }, [chartAvailable, columns, rows, labelColumn, valueColumn]);

  const chartTitle =
    data?.chart_defaults?.chart_title ??
    (chartSeries ? `${chartSeries.valueLabel} by ${humanizeColumn(columns[labelColumn] ?? "Category")}` : "");

  if (!data) {
    return (
      <div className="analytics-preview-empty">
        {isRunning ? (
          <>
            <p className="ask-activity mb-0" role="status" aria-live="polite">
              {activityStatus ?? "Starting…"}
            </p>
            <AnalyticsLoadingDots />
          </>
        ) : (
          <p className="analytics-preview-placeholder">Ask anything to analyze and preview</p>
        )}
      </div>
    );
  }

  return (
    <div className="analytics-dashboard">
      <header className="analytics-dashboard-header">
        <div>
          <h2 className="analytics-dashboard-title">{data.title}</h2>
          <div className="mt-1 flex flex-wrap gap-2">
            {data.domain_name && <span className="badge">Domain: {data.domain_name}</span>}
            {data.query_kind === "structured" && <span className="badge">SQL</span>}
          </div>
        </div>
        {onToggleFullscreen && (
          <button
            type="button"
            className="btn btn-secondary analytics-fullscreen-btn"
            onClick={onToggleFullscreen}
            aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
          >
            {isFullscreen ? "Exit full screen" : "Full screen"}
          </button>
        )}
      </header>

      {(chartAvailable || kpiAvailable || tableAvailable || summaryAvailable) && (
        <AnalyticsViewControls
          columns={columns}
          numericColumns={numericCols}
          visibility={visibility}
          onVisibilityChange={setVisibility}
          chartType={chartType}
          onChartTypeChange={setChartType}
          labelColumn={labelColumn}
          onLabelColumnChange={setLabelColumn}
          valueColumn={valueColumn}
          onValueColumnChange={setValueColumn}
          chartAvailable={chartAvailable}
          kpiAvailable={kpiAvailable}
          tableAvailable={tableAvailable}
          summaryAvailable={summaryAvailable}
        />
      )}

      {summaryAvailable && visibility.summary && (
        <p className="analytics-summary">{data.summary}</p>
      )}

      {notesAvailable && (
        <div className="analytics-notes" role="note">
          <p className="analytics-notes-title">Data not available</p>
          <ul className="analytics-notes-list">
            {data.notes!.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {kpiAvailable && visibility.kpi && (
        <div className="analytics-kpi-grid">
          {data.kpis!.map((w, i) => (
            <div key={`kpi-${i}`} className="analytics-kpi">
              <p className="analytics-kpi-label">{w.label}</p>
              <p className="analytics-kpi-value">{w.value}</p>
              {w.hint && <p className="analytics-kpi-hint">{w.hint}</p>}
            </div>
          ))}
        </div>
      )}

      <div className="analytics-widget-grid">
        {tableAvailable && visibility.table && (
          <div className="analytics-widget-card">
            <h3 className="analytics-widget-title">Data table</h3>
            <div className="table-wrap">
              <table className="data analytics-table">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{humanizeColumn(c)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, ri) => (
                    <tr key={ri}>
                      {columns.map((_, ci) => (
                        <td key={ci}>{formatCell(row[ci])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.total_rows != null && data.total_rows > rows.length && (
              <p className="analytics-table-note">
                Showing {rows.length} of {data.total_rows} rows
              </p>
            )}
          </div>
        )}
        {chartAvailable && visibility.chart && chartSeries && (
          <div className="analytics-widget-card analytics-widget-card--chart">
            <AnalyticsChart
              chartType={chartType}
              title={chartTitle}
              labels={chartSeries.labels}
              values={chartSeries.values}
              valueLabel={chartSeries.valueLabel}
            />
          </div>
        )}
      </div>

      {!summaryAvailable && !kpiAvailable && !tableAvailable && !chartAvailable && (
        <p className="analytics-summary" style={{ color: "var(--color-text-muted)" }}>
          No structured results to display. Try a question against postgres catalog data.
        </p>
      )}

      {data.sql && (
        <details className="analytics-sql-details">
          <summary className="cursor-pointer text-xs font-medium" style={{ color: "var(--color-text-muted)" }}>
            View SQL
          </summary>
          <pre className="analytics-sql">{data.sql}</pre>
        </details>
      )}
    </div>
  );
}
