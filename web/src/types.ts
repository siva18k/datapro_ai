export interface Domain {
  id: string;
  slug: string;
  name: string;
  description: string;
  color: string;
  enabled: boolean;
}

export interface Dataset {
  id: string;
  domain_id: string;
  domain_slug: string;
  domain_name: string;
  slug: string;
  name: string;
  description: string;
  source_type: string;
  connector: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

export interface DatasetSummary {
  connector: string;
  name: string;
  host?: string;
  schema?: string;
  table_count?: number;
  file_count?: number;
  chunk_count?: number;
  base_url?: string;
  url?: string;
}

export type TableRole = "fact" | "lookup" | "excluded";

export interface TableMeta {
  id: string;
  source_id: string;
  table_schema: string;
  table_name: string;
  definition: string;
  enabled: boolean;
  table_role?: TableRole;
}

export interface ColumnMeta {
  id: string;
  table_metadata_id: string;
  column_name: string;
  data_type: string;
  labels: string[];
  description: string;
}

export interface ColumnSyncStats {
  added: number;
  updated: number;
  removed: number;
  unchanged: number;
}

export interface SyncColumnsResult {
  columns: ColumnMeta[];
  stats: ColumnSyncStats;
}

export interface RagProfile {
  id: string;
  source_id: string;
  chunk_size: number;
  chunk_overlap: number;
  embedding_model: string;
  instructions: string;
  metadata_text: string;
  last_ingested_at?: string;
}

export interface AskSource {
  source: string;
  chunk_id: string;
  text: string;
  distance?: number;
}

export interface AskResponse {
  answer: string;
  question?: string;
  domain_name?: string;
  routing_method?: string;
  routing_confidence?: number;
  query_kind?: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  sources: AskSource[];
}

export interface AskExportResponse {
  format: string;
  content_type: string;
  content: string;
  filename: string;
}

export interface KpiWidget {
  type: "kpi";
  label: string;
  value: string;
  hint?: string;
}

export interface TableWidget {
  type: "table";
  title?: string;
  columns: string[];
  rows: unknown[][];
  total_rows?: number;
}

export interface AnalyticsChartDefaults {
  chart_type: "bar" | "line" | "pie";
  label_column: number;
  value_column: number;
  chart_title?: string;
}

export interface AnalyticsResponse {
  title: string;
  summary?: string;
  columns?: string[];
  rows?: unknown[][];
  total_rows?: number;
  chart_defaults?: AnalyticsChartDefaults;
  kpis?: KpiWidget[];
  domain_name?: string;
  routing_method?: string;
  query_kind?: string;
  sql?: string;
  notes?: string[];
}

export const CONNECTOR_LABELS: Record<string, string> = {
  postgres: "Database",
  upload: "Uploaded files",
  file_path: "Local files",
  api: "API",
  sharepoint: "SharePoint",
  web_url: "Web link",
};
