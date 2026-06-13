import type {
  AnalyticsResponse,
  AskExportResponse,
  AskResponse,
  ReadinessResponse,
  PipelineTraceStep,
  ColumnMeta,
  SyncColumnsResult,
  Dataset,
  DatasetSummary,
  Domain,
  RagProfile,
  TableMeta,
} from "../types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    throw new Error("API server is not reachable. Start it from Settings or run uvicorn on port 8080.");
  }
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") throw new Error(body.detail);
      if (Array.isArray(body.detail)) {
        throw new Error(body.detail.map((d) => d.msg).filter(Boolean).join("; ") || res.statusText);
      }
    } catch (e) {
      if (e instanceof Error && e.message !== text) throw e;
    }
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  readiness: () => request<ReadinessResponse>("/readiness"),
  stats: () => request<{ total_chunks: number; ingested_files: number }>("/stats"),

  listDomains: () => request<Domain[]>("/domains"),
  createDomain: (name: string, description = "") =>
    request<Domain>("/domains", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),
  updateDomain: (id: string, data: Partial<Domain>) =>
    request<Domain>(`/domains/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDomain: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/domains/${id}`, { method: "DELETE" }),

  listDatasets: (domainId: string) => request<Dataset[]>(`/domains/${domainId}/datasets?enabled_only=false`),
  createDataset: (domainId: string, data: { name: string; description?: string; connector: string; config?: object }) =>
    request<Dataset>(`/domains/${domainId}/datasets`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getDataset: (id: string) => request<Dataset>(`/datasets/${id}`),
  updateDataset: (id: string, data: Partial<Dataset>) =>
    request<Dataset>(`/datasets/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDataset: (id: string) =>
    request<{ deleted: boolean; chunks_removed: number; name: string }>(`/datasets/${id}`, { method: "DELETE" }),
  datasetSummary: (id: string) => request<DatasetSummary>(`/datasets/${id}/summary`),

  testConnection: (id: string) =>
    request<{ ok: boolean; message: string }>(`/datasets/${id}/test-connection`, { method: "POST" }),
  remoteTables: (id: string) => request<{ tables: string[] }>(`/datasets/${id}/remote-tables`),
  catalogTables: (id: string) => request<TableMeta[]>(`/datasets/${id}/tables`),
  addTables: (id: string, table_names: string[]) =>
    request<TableMeta[]>(`/datasets/${id}/tables`, {
      method: "POST",
      body: JSON.stringify({ table_names }),
    }),
  updateTable: (
    id: string,
    data: { definition?: string; table_role?: string },
  ) => request(`/tables/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteTable: (id: string) => request(`/tables/${id}`, { method: "DELETE" }),
  syncColumns: (tableId: string) => request<SyncColumnsResult>(`/tables/${tableId}/sync-columns`, { method: "POST" }),
  listColumns: (tableId: string) => request<ColumnMeta[]>(`/tables/${tableId}/columns`),
  updateColumn: (id: string, data: { labels?: string[]; description?: string }) =>
    request(`/columns/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  getDefinition: (id: string) => request<{ markdown: string; path: string }>(`/datasets/${id}/definition`),
  saveDefinition: (id: string, markdown: string) =>
    request(`/datasets/${id}/definition`, { method: "PUT", body: JSON.stringify({ markdown }) }),
  draftDefinition: (id: string) => request<{ markdown: string }>(`/datasets/${id}/definition/draft`, { method: "POST" }),

  listFiles: (id: string) =>
    request<{ name: string; size: number; ingested: boolean; chunks: number }[]>(`/datasets/${id}/files`),
  supportedFileTypes: () =>
    request<{ extensions: string[]; accept: string }>("/datasets/supported-file-types"),
  uploadFiles: async (id: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    const res = await fetch(`${BASE}/datasets/${id}/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (body.detail) throw new Error(body.detail);
      } catch (e) {
        if (e instanceof Error && e.message !== text) throw e;
      }
      throw new Error(text || res.statusText);
    }
    return res.json() as Promise<{ saved: string[]; skipped: { name: string; reason: string }[] }>;
  },
  ingest: (id: string, file_names: string[]) =>
    request(`/datasets/${id}/ingest`, { method: "POST", body: JSON.stringify({ file_names }) }),

  ask: (data: {
    question: string;
    top_k?: number;
    domain_override?: string;
    domain_overrides?: string[];
    backend?: string;
    model?: string;
    debug?: boolean;
  }) => request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(data) }),

  askStream: async (
    data: {
      question: string;
      top_k?: number;
      domain_override?: string;
      domain_overrides?: string[];
      backend?: string;
      model?: string;
      debug?: boolean;
    },
    onStatus: (message: string) => void,
    onTrace?: (step: PipelineTraceStep) => void,
  ): Promise<AskResponse> => {
    const res = await fetch(`${BASE}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const text = await res.text();
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (typeof body.detail === "string") throw new Error(body.detail);
      } catch (e) {
        if (e instanceof Error && e.message !== text) throw e;
      }
      throw new Error(text || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: AskResponse | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as {
          type: string;
          message?: string;
          data?: AskResponse;
          step?: PipelineTraceStep;
          rag?: boolean;
          mcp?: boolean;
        };
        if (event.type === "status" && event.message) onStatus(event.message);
        if (event.type === "trace" && event.step) onTrace?.(event.step);
        if (event.type === "result" && event.data) result = event.data;
        if (event.type === "error") throw new Error(event.message || "Ask failed");
      }
    }

    if (!result) throw new Error("Ask finished without a result");
    return result;
  },

  analyticsStream: async (
    data: {
      prompt: string;
      domain_override?: string;
      domain_overrides?: string[];
      backend?: string;
      model?: string;
    },
    onStatus: (message: string) => void,
  ): Promise<AnalyticsResponse> => {
    const res = await fetch(`${BASE}/analytics/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const text = await res.text();
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (typeof body.detail === "string") throw new Error(body.detail);
      } catch (e) {
        if (e instanceof Error && e.message !== text) throw e;
      }
      throw new Error(text || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: AnalyticsResponse | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as {
          type: string;
          message?: string;
          data?: AnalyticsResponse;
        };
        if (event.type === "status" && event.message) onStatus(event.message);
        if (event.type === "result" && event.data) result = event.data;
        if (event.type === "error") throw new Error(event.message || "Analytics failed");
      }
    }

    if (!result) throw new Error("Analytics finished without a result");
    return result;
  },

  getRag: (sourceId: string) => request<{ source: Dataset; profile: RagProfile }>(`/rag/sources/${sourceId}`),
  updateRag: (sourceId: string, data: Partial<RagProfile>) =>
    request<RagProfile>(`/rag/sources/${sourceId}`, { method: "PATCH", body: JSON.stringify(data) }),
  reingest: (sourceId: string) => request(`/rag/sources/${sourceId}/reingest`, { method: "POST" }),
  askExport: (data: {
    format: string;
    question: string;
    answer: string;
    domain_name?: string;
    sql?: string;
    columns?: string[];
    rows?: unknown[][];
  }) =>
    request<AskExportResponse>("/ask/export", { method: "POST", body: JSON.stringify(data) }),

  indexCatalog: (sourceId: string) =>
    request<{
      catalog_chunks: number;
      metadata_tables: number;
      lookup_tables: number;
      removed_chunks: number;
    }>(`/rag/sources/${sourceId}/index-catalog`, { method: "POST" }),

  mcpStatus: () => request<McpStatusResponse>("/mcp/status"),

  mcpStart: () =>
    request<McpActionResponse>("/mcp/start", { method: "POST" }),

  mcpStop: () =>
    request<McpActionResponse>("/mcp/stop", { method: "POST" }),

  mcpRestart: () =>
    request<McpActionResponse>("/mcp/restart", { method: "POST" }),

  backendStatus: () => request<BackendStatusResponse>("/backend/status"),

  backendStart: () =>
    request<BackendActionResponse>("/backend/start", { method: "POST" }),

  backendStop: () =>
    request<BackendActionResponse>("/backend/stop", { method: "POST" }),

  backendRestart: () =>
    request<BackendActionResponse>("/backend/restart", { method: "POST" }),

  backendLog: (lines = 80) => request<{ log: string }>(`/backend/log?lines=${lines}`),

  mcpCapabilities: () =>
    request<{
      tools: { name: string; description?: string }[];
      resources: { name?: string; uri?: string }[];
      prompts: { name: string; description?: string }[];
    }>("/mcp/capabilities"),

  mcpLog: (lines = 80) => request<{ log: string }>(`/mcp/log?lines=${lines}`),

  mcpRegistry: () => request<McpRegistryResponse>("/mcp/registry"),

  updateMcpPrompt: (
    name: string,
    data: { description?: string; template?: string; enabled?: boolean },
  ) =>
    request<{ ok: boolean; requires_restart: boolean; prompt: McpRegistryPrompt }>(
      `/mcp/registry/prompts/${encodeURIComponent(name)}`,
      { method: "PUT", body: JSON.stringify(data) },
    ),

  previewMcpPrompt: (name: string, arguments_?: Record<string, string>) =>
    request<{ preview: string }>(`/mcp/prompts/${encodeURIComponent(name)}/preview`, {
      method: "POST",
      body: JSON.stringify({ arguments: arguments_ ?? {} }),
    }),

  mcpToolDetail: (name: string) =>
    request<McpToolDetailResponse>(`/mcp/tools/${encodeURIComponent(name)}`),

  mcpResourceMeta: (uri: string) =>
    request<McpResourceMetaResponse>(`/mcp/resources/meta?uri=${encodeURIComponent(uri)}`),

  previewMcpResource: (uri: string, params?: Record<string, string>) =>
    request<McpResourcePreviewResponse>("/mcp/resources/preview", {
      method: "POST",
      body: JSON.stringify({ uri, params: params ?? {} }),
    }),

  mcpBindings: (domainId: string) =>
    request<McpBindingsResponse>(`/mcp/bindings?domain_id=${encodeURIComponent(domainId)}`),

  mcpBindingCatalog: () => request<McpBindingCatalogResponse>("/mcp/binding-catalog"),

  addMcpBinding: (data: {
    domain_id: string;
    mcp_server_id: string;
    capability_type: "tool" | "resource" | "prompt";
    capability_name: string;
  }) =>
    request<{ ok: boolean; binding: McpBoundCapability }>("/mcp/bindings", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeMcpBinding: (bindingId: string) =>
    request<{ ok: boolean }>(`/mcp/bindings/${encodeURIComponent(bindingId)}`, {
      method: "DELETE",
    }),

  setMcpBinding: (data: {
    domain_id: string;
    capability_type: "tool" | "resource" | "prompt";
    capability_name: string;
    enabled: boolean;
    source_id?: string | null;
    mcp_server_id?: string | null;
  }) =>
    request<{ ok: boolean }>("/mcp/bindings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  listMcpServers: () =>
    request<{ servers: McpServerRecord[]; dismissed_optional?: McpOptionalServerSpec[] }>(
      "/mcp/servers",
    ),

  restoreMcpServer: (slug: string) =>
    request<{ ok: boolean; server: McpServerRecord }>(
      `/mcp/servers/restore/${encodeURIComponent(slug)}`,
      { method: "POST" },
    ),

  createMcpServer: (data: {
    name: string;
    url: string;
    description?: string;
    server_kind?: "public" | "enterprise";
    transport?: string;
  }) =>
    request<{ ok: boolean; server: McpServerRecord }>("/mcp/servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateMcpServer: (
    serverId: string,
    data: {
      name?: string;
      url?: string;
      description?: string;
      server_kind?: "public" | "enterprise";
      transport?: string;
      enabled?: boolean;
    },
  ) =>
    request<{ ok: boolean; server: McpServerRecord }>(`/mcp/servers/${encodeURIComponent(serverId)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteMcpServer: (serverId: string) =>
    request<{ ok: boolean }>(`/mcp/servers/${encodeURIComponent(serverId)}`, {
      method: "DELETE",
    }),

  startMcpServer: (serverId: string) =>
    request<McpServerActionResponse>(`/mcp/servers/${encodeURIComponent(serverId)}/start`, {
      method: "POST",
    }),

  stopMcpServer: (serverId: string) =>
    request<McpServerActionResponse>(`/mcp/servers/${encodeURIComponent(serverId)}/stop`, {
      method: "POST",
    }),

  mcpServerCapabilities: (serverId: string) =>
    request<McpServerCapabilitiesResponse>(`/mcp/servers/${encodeURIComponent(serverId)}/capabilities`),

  getSettings: () => request<AppSettings>("/settings"),
  saveSettings: (data: {
    database?: DatabaseSettingsPayload;
    mcp_url?: string;
    embedding_model?: string;
    llm?: LlmSettingsPayload;
    mistral_api_key?: string;
  }) => request<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(data) }),
  testDatabase: (database: DatabaseSettingsPayload) =>
    request<{ ok: boolean; message: string }>("/settings/test-database", {
      method: "POST",
      body: JSON.stringify({ database }),
    }),

  listDbConnections: () => request<SavedDbConnection[]>("/connections"),
  getDbConnectionConfig: (id: string) =>
    request<Record<string, unknown>>(`/connections/${id}/config`),
  createDbConnection: (data: DbConnectionPayload) =>
    request<SavedDbConnection>("/connections", { method: "POST", body: JSON.stringify(data) }),
  updateDbConnection: (id: string, data: Partial<DbConnectionPayload>) =>
    request<SavedDbConnection>(`/connections/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteDbConnection: (id: string) =>
    request<{ deleted: boolean }>(`/connections/${id}`, { method: "DELETE" }),
  testDbConnection: (data: DbConnectionPayload) =>
    request<{ ok: boolean; message: string }>("/connections/test", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export interface DatabaseSettingsPayload {
  use_database_url: boolean;
  database_url?: string;
  host?: string;
  port?: number;
  user?: string;
  password?: string;
  database?: string;
  schema?: string;
  sslmode?: string;
}

export interface DbConnectionPayload {
  name: string;
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
  schema: string;
  sslmode: string;
}

export interface SavedDbConnection {
  id: string;
  name: string;
  host: string;
  port: number;
  user: string;
  database: string;
  schema: string;
  sslmode: string;
  password_set: boolean;
}

export interface McpStatusResponse {
  url: string;
  port: number;
  reachable: boolean;
  running: boolean;
  status_label: string;
  active_pid: number | null;
  listener_pids: number[];
  source: string;
  default_url: string;
}

export interface McpActionResponse extends McpStatusResponse {
  ok: boolean;
  message: string;
}

export interface McpBindingItem {
  id?: string;
  name: string;
  enabled: boolean;
  description?: string;
  uri?: string;
  mcp_server_id?: string;
  server_name?: string;
  server_slug?: string;
  server_url?: string;
  server_kind?: string;
}

export interface McpBoundCapability extends McpBindingItem {
  id: string;
  domain_id: string;
}

export interface McpBindingsResponse {
  domain_id: string;
  bindings: {
    tools: McpBindingItem[];
    resources: McpBindingItem[];
    prompts: McpBindingItem[];
  };
}

export interface McpServerRecord {
  id: string;
  slug: string;
  name: string;
  description: string;
  url: string;
  server_kind: "builtin" | "public" | "enterprise";
  transport: string;
  enabled: boolean;
  is_builtin: boolean;
  can_manage?: boolean;
  reachable?: boolean;
  running?: boolean;
  status_label?: string;
  runtime?: string;
  port?: number;
}

export interface McpServerActionResponse {
  ok: boolean;
  message: string;
  server: McpServerRecord;
}

export interface McpOptionalServerSpec {
  slug: string;
  name: string;
  description: string;
  default_url: string;
  server_kind: string;
}

export interface McpCatalogCapability {
  name: string;
  description?: string;
  uri?: string;
}

export interface McpBindingCatalogEntry {
  server: McpServerRecord;
  reachable: boolean;
  tools: McpCatalogCapability[];
  resources: McpCatalogCapability[];
  prompts: McpCatalogCapability[];
}

export interface McpBindingCatalogResponse {
  servers: McpBindingCatalogEntry[];
}

export interface McpServerCapabilitiesResponse {
  reachable: boolean;
  tools: McpCatalogCapability[];
  resources: McpCatalogCapability[];
  prompts: McpCatalogCapability[];
}

export interface McpRegistryPrompt {
  name: string;
  description: string;
  template: string;
  enabled: boolean;
}

export interface McpRegistryResponse {
  registry_path: string;
  server: Record<string, unknown>;
  tools: { name: string; description: string; enabled: boolean }[];
  resources: { uri: string; name: string; description: string; mime_type: string; enabled: boolean }[];
  prompts: McpRegistryPrompt[];
}

export interface McpToolDetailResponse {
  name: string;
  description: string;
  enabled_in_registry: boolean;
  implementation: string;
  implementation_path: string;
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  live_description: string | null;
}

export interface McpResourceMetaResponse {
  uri: string;
  name: string;
  description: string;
  mime_type: string;
  enabled: boolean;
  parameters: string[];
}

export interface McpResourcePreviewResponse {
  uri_template: string;
  uri: string;
  content: string;
  truncated: boolean;
  mime_type?: string;
}

export interface BackendStatusResponse {
  url: string;
  health_url: string;
  host: string;
  port: number;
  reachable: boolean;
  running: boolean;
  status_label: string;
  active_pid: number | null;
  listener_pids: number[];
  source: string;
  stopping_self: boolean;
  log_path: string;
}

export interface BackendActionResponse extends BackendStatusResponse {
  ok: boolean;
  message: string;
}

export interface LlmBackendOption {
  id: string;
  label: string;
  default_model: string;
}

export interface LlmSettingsPublic {
  default_backend: string;
  default_model: string;
  ollama_base_url: string;
  mistral_api_key_set: boolean;
  openai_api_key_set: boolean;
  anthropic_api_key_set: boolean;
  gemini_api_key_set: boolean;
  openrouter_api_key_set: boolean;
}

export interface LlmSettingsPayload {
  default_backend?: string;
  default_model?: string;
  ollama_base_url?: string;
  mistral_api_key?: string;
  openai_api_key?: string;
  anthropic_api_key?: string;
  gemini_api_key?: string;
  openrouter_api_key?: string;
}

export interface AppSettings {
  env_path: string;
  database: {
    host: string;
    port: number;
    user: string;
    database: string;
    schema: string;
    sslmode: string;
    database_url: string;
    use_database_url: boolean;
    password_set: boolean;
  };
  mcp_url: string;
  embedding_model: string;
  embedding_model_options: string[];
  llm_backends: LlmBackendOption[];
  llm: LlmSettingsPublic;
  mistral_api_key_set: boolean;
}
