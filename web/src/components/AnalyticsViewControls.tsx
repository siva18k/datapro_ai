import type { ChartType } from "../utils/analyticsData";
import { humanizeColumn } from "../utils/analyticsData";

export interface ViewVisibility {
  summary: boolean;
  kpi: boolean;
  chart: boolean;
  table: boolean;
}

interface Props {
  columns: string[];
  numericColumns: number[];
  visibility: ViewVisibility;
  onVisibilityChange: (next: ViewVisibility) => void;
  chartType: ChartType;
  onChartTypeChange: (t: ChartType) => void;
  labelColumn: number;
  onLabelColumnChange: (idx: number) => void;
  valueColumn: number;
  onValueColumnChange: (idx: number) => void;
  chartAvailable: boolean;
  kpiAvailable: boolean;
  tableAvailable: boolean;
  summaryAvailable: boolean;
}

export function AnalyticsViewControls({
  columns,
  numericColumns,
  visibility,
  onVisibilityChange,
  chartType,
  onChartTypeChange,
  labelColumn,
  onLabelColumnChange,
  valueColumn,
  onValueColumnChange,
  chartAvailable,
  kpiAvailable,
  tableAvailable,
  summaryAvailable,
}: Props) {
  const toggle = (key: keyof ViewVisibility) => {
    onVisibilityChange({ ...visibility, [key]: !visibility[key] });
  };

  return (
    <div className="analytics-toolbar">
      <div className="analytics-toolbar-group">
        <span className="analytics-toolbar-label">Show</span>
        {summaryAvailable && (
          <ToggleChip active={visibility.summary} onClick={() => toggle("summary")}>
            Summary
          </ToggleChip>
        )}
        {kpiAvailable && (
          <ToggleChip active={visibility.kpi} onClick={() => toggle("kpi")}>
            KPIs
          </ToggleChip>
        )}
        {chartAvailable && (
          <ToggleChip active={visibility.chart} onClick={() => toggle("chart")}>
            Chart
          </ToggleChip>
        )}
        {tableAvailable && (
          <ToggleChip active={visibility.table} onClick={() => toggle("table")}>
            Table
          </ToggleChip>
        )}
      </div>

      {chartAvailable && visibility.chart && (
        <>
          <div className="analytics-toolbar-group">
            <span className="analytics-toolbar-label">Chart</span>
            {(["bar", "line", "pie"] as const).map((t) => (
              <ToggleChip key={t} active={chartType === t} onClick={() => onChartTypeChange(t)}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </ToggleChip>
            ))}
          </div>
          <div className="analytics-toolbar-group">
            <label className="analytics-axis-select">
              <span className="analytics-toolbar-label">X axis</span>
              <select
                value={labelColumn}
                onChange={(e) => onLabelColumnChange(Number(e.target.value))}
              >
                {columns.map((c, i) => (
                  <option key={i} value={i}>
                    {humanizeColumn(c)}
                  </option>
                ))}
              </select>
            </label>
            <label className="analytics-axis-select">
              <span className="analytics-toolbar-label">Y axis</span>
              <select
                value={valueColumn}
                onChange={(e) => onValueColumnChange(Number(e.target.value))}
              >
                {numericColumns.map((i) => (
                  <option key={i} value={i}>
                    {humanizeColumn(columns[i])}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}
    </div>
  );
}

function ToggleChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`analytics-toggle-chip${active ? " analytics-toggle-chip--active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}
