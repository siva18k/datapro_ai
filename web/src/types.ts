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

export interface DatasetRelationship {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  source: string;
  confidence: string;
  note: string;
}

export interface DatasetRelationshipsResult {
  relationships: DatasetRelationship[];
  markdown_section: string;
  merged_markdown: string;
  table_count: number;
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

export interface PipelineChunkRef {
  source_file: string;
  chunk_id: string;
  distance?: number;
  domain_id?: string;
  source_id?: string;
  text_preview?: string;
  verify_sql: string;
}

export interface PipelineTraceDetail {
  question?: string;
  top_k?: number;
  domain_override?: string;
  domain_overrides?: string[];
  domain_id?: string;
  domain_name?: string;
  routing_method?: string;
  routing_confidence?: number;
  execution_kind?: string;
  source_id?: string;
  source_name?: string;
  retrieval?: string;
  retrieval_query?: string;
  mcp_url?: string;
  mcp_tool?: string;
  mcp_arguments?: Record<string, unknown>;
  llm_prompt?: string;
  sql?: string;
  columns?: string[];
  row_count?: number;
  chunks?: PipelineChunkRef[];
}

export interface PipelineTraceStep {
  message: string;
  phase: string;
  detail?: PipelineTraceDetail;
}

export interface AskResponse {
  answer: string;
  question?: string;
  domain_name?: string;
  routing_method?: string;
  routing_confidence?: number;
  query_kind?: string;
  used_rag?: boolean;
  used_mcp?: boolean;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  sources: AskSource[];
  session_reset?: boolean;
  session_summary?: string | null;
  new_topic?: boolean;
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

export interface TimePeriod {
  label: string;
  start: string;
  end_exclusive: string;
  granularity?: string;
  calendar_year?: number;
  quarter?: number;
  fiscal_year?: number;
  fiscal_quarter?: number;
}

export interface TimeContext {
  requirement: string;
  reference_date?: string;
  fiscal_year_start_month?: number;
  granularity?: string;
  source?: "mcp" | "local";
  periods: TimePeriod[];
}

export interface AnalyticsResponse {
  title: string;
  summary?: string;
  columns?: string[];
  rows?: unknown[][];
  total_rows?: number;
  chart_defaults?: AnalyticsChartDefaults;
  time_context?: TimeContext;
  kpis?: KpiWidget[];
  domain_name?: string;
  routing_method?: string;
  query_kind?: string;
  sql?: string;
  notes?: string[];
  session_reset?: boolean;
  session_summary?: string | null;
  new_topic?: boolean;
}

export interface AgentCapabilities {
  kpi_check?: boolean;
  generate_report?: boolean;
  send_email?: boolean;
  email_to?: string;
}

export interface AgentToolBinding {
  id?: string;
  agent_id?: string;
  mcp_server_id: string;
  tool_name: string;
  server_name?: string;
  server_slug?: string;
}

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string;
  instructions: string;
  capabilities: AgentCapabilities;
  enabled: boolean;
  domain_slugs?: string[];
  domain_warnings?: string[];
  tools?: AgentToolBinding[];
  created_at?: string;
  updated_at?: string;
}

export interface AgentRunStep {
  step_id: string;
  message: string;
  status?: string;
  payload?: Record<string, unknown>;
}

export interface AgentRunResult {
  agent_id: string;
  kpi_passed?: boolean | null;
  report_generated?: boolean;
  email_preview?: boolean;
}

export interface AgentFlowStep {
  agent_id: string;
  handoff?: string;
  agent_name?: string;
  agent_slug?: string;
}

export interface AgentFlowGraphNode {
  id: string;
  agent_id: string;
  column: 0 | 1;
  agent_name?: string;
  agent_slug?: string;
}

export interface AgentFlowGraphEdge {
  from: string;
  to: string;
  handoff?: string;
}

export interface AgentFlowGraph {
  v: 2;
  nodes: AgentFlowGraphNode[];
  edges: AgentFlowGraphEdge[];
}

export interface AgentFlow {
  id: string;
  slug: string;
  name: string;
  description: string;
  instructions: string;
  steps: AgentFlowStep[] | AgentFlowGraph;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AgentFlowRunResult {
  flow_id: string;
  completed_steps: number;
  total_steps: number;
  failed?: boolean;
  error?: string;
  report_html?: string | null;
  agent_results?: {
    agent_id: string;
    agent_name: string;
    agent_slug: string;
    step_index: number;
    summary?: string;
  }[];
}

export interface ReadinessComponent {
  ok: boolean;
  message?: string | null;
}

export interface ReadinessResponse {
  ok: boolean;
  components: {
    rag_database: ReadinessComponent;
    knowledge_chunks: ReadinessComponent;
    catalog: ReadinessComponent;
    metadata: ReadinessComponent;
  };
  issues: string[];
}

export const CONNECTOR_LABELS: Record<string, string> = {
  postgres: "Database",
  upload: "Uploaded files",
  file_path: "Local files",
  api: "API",
  sharepoint: "SharePoint",
  web_url: "Web link",
};
