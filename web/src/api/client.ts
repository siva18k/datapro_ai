import type {
  Agent,
  AgentFlow,
  AgentFlowRunResult,
  AgentRunResult,
  AgentToolBinding,
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
  FileRagRow,
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
  const text = await res.text();
  if (!res.ok) {
    if (!text.trim()) {
      throw new Error(
        `Request failed (${res.status}${res.statusText ? ` ${res.statusText}` : ""}). ` +
          "Is the API server running on port 8080?",
      );
    }
    try {
      const body = JSON.parse(text) as { detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") throw new Error(body.detail);
      if (Array.isArray(body.detail)) {
        throw new Error(body.detail.map((d) => d.msg).filter(Boolean).join("; ") || res.statusText);
      }
    } catch (e) {
      if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
    }
    throw new Error(text || res.statusText);
  }
  if (!text.trim()) {
    throw new Error("Empty response from API — is the server running on port 8080?");
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("Invalid JSON from API — the server may have returned an error page.");
  }
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  readiness: () => request<ReadinessResponse>("/readiness"),
  stats: () =>
    request<{
      total_chunks: number;
      ingested_files: number;
      domain_count: number;
      dataset_count: number;
    }>("/stats"),

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

  listDomainPrompts: (domainId: string) =>
    request<DomainPrompt[]>(`/domains/${domainId}/prompts`),
  createDomainPrompt: (
    domainId: string,
    data: {
      slug: string;
      name: string;
      description?: string;
      template?: string;
      enabled?: boolean;
      bind?: boolean;
    },
  ) =>
    request<DomainPrompt>(`/domains/${domainId}/prompts`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateDomainPrompt: (
    domainId: string,
    promptId: string,
    data: Partial<Pick<DomainPrompt, "slug" | "name" | "description" | "template" | "enabled">>,
  ) =>
    request<DomainPrompt>(`/domains/${domainId}/prompts/${promptId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteDomainPrompt: (domainId: string, promptId: string) =>
    request<{ deleted: boolean; id: string }>(`/domains/${domainId}/prompts/${promptId}`, {
      method: "DELETE",
    }),

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
  listDatasetAssets: (id: string) =>
    request<{ assets: DatasetAsset[]; connector: string }>(`/datasets/${id}/assets`),
  syncDataset: (id: string, data?: { asset_ids?: string[]; full?: boolean }) =>
    request<DatasetSyncResult>(`/datasets/${id}/sync`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),

  testConnection: (id: string) =>
    request<{ ok: boolean; message: string }>(`/datasets/${id}/test-connection`, { method: "POST" }),
  remoteTables: (id: string) => request<{ tables: string[] }>(`/datasets/${id}/remote-tables`),
  catalogTables: (id: string) => request<TableMeta[]>(`/datasets/${id}/tables`),
  getDatasetRag: (id: string) => request<import("../types").DatasetRagSettings>(`/datasets/${id}/rag`),
  saveDatasetRagSettings: (
    id: string,
    data: {
      profile?: { chunk_size?: number; chunk_overlap?: number; instructions?: string };
      tables?: Array<{
        id: string;
        rag_enabled?: boolean;
        chunk_size?: number | null;
        chunk_overlap?: number | null;
      }>;
      files?: Array<{
        file_name: string;
        rag_enabled?: boolean;
        chunk_size?: number | null;
        chunk_overlap?: number | null;
      }>;
    },
  ) =>
    request<{ profile: RagProfile; tables?: TableMeta[]; files?: FileRagRow[]; chunks_removed?: number }>(
      `/datasets/${id}/rag/settings`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  ingestDatasetRag: (
    id: string,
    data?: { table_ids?: string[]; file_names?: string[] },
  ) =>
    request<{ catalog_chunks?: number; total_chunks?: number; skipped?: boolean; message?: string }>(
      `/datasets/${id}/rag/ingest`,
      { method: "POST", body: JSON.stringify(data ?? {}) },
    ),
  addTables: (id: string, table_names: string[]) =>
    request<TableMeta[]>(`/datasets/${id}/tables`, {
      method: "POST",
      body: JSON.stringify({ table_names }),
    }),
  updateTable: (
    id: string,
    data: {
      definition?: string;
      table_role?: string;
      rag_enabled?: boolean;
      chunk_size?: number | null;
      chunk_overlap?: number | null;
    },
  ) => request(`/tables/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteTable: (id: string) => request(`/tables/${id}`, { method: "DELETE" }),
  syncColumns: (tableId: string) => request<SyncColumnsResult>(`/tables/${tableId}/sync-columns`, { method: "POST" }),
  listColumns: (tableId: string) => request<ColumnMeta[]>(`/tables/${tableId}/columns`),
  updateColumn: (id: string, data: { labels?: string[]; description?: string }) =>
    request(`/columns/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  getDefinition: (id: string) => request<{ markdown: string; path: string }>(`/datasets/${id}/definition`),
  getDefinitionRelationships: (id: string) =>
    request<import("../types").DatasetRelationshipsResult>(`/datasets/${id}/definition/relationships`),
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
        if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
      }
      throw new Error(text || res.statusText);
    }
    const text = await res.text();
    if (!text.trim()) {
      throw new Error("Empty response from API — is the server running on port 8080?");
    }
    try {
      return JSON.parse(text) as { saved: string[]; skipped: { name: string; reason: string }[] };
    } catch {
      throw new Error("Invalid JSON from upload response.");
    }
  },
  ingest: (id: string, file_names: string[]) =>
    request(`/datasets/${id}/ingest`, { method: "POST", body: JSON.stringify({ file_names }) }),

  ask: (data: {
    question: string;
    top_k?: number;
    domain_override?: string;
    domain_overrides?: string[];
    conversation_history?: {
      role: string;
      content: string;
      question?: string;
      sql?: string;
      columns?: string[];
      rows?: unknown[][];
    }[];
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
      conversation_history?: {
      role: string;
      content: string;
      question?: string;
      sql?: string;
      columns?: string[];
      rows?: unknown[][];
    }[];
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
        if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
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
      conversation_history?: {
        role: string;
        content: string;
        question?: string;
        sql?: string;
        columns?: string[];
        rows?: unknown[][];
      }[];
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
        if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
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

  listAgents: () => request<Agent[]>("/agents"),
  getAgent: (id: string) => request<Agent>(`/agents/${id}`),
  createAgent: (data: { name: string; description?: string; instructions?: string; capabilities?: Agent["capabilities"] }) =>
    request<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (id: string, data: Partial<Agent>) =>
    request<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAgent: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/agents/${id}`, { method: "DELETE" }),
  setAgentTools: (id: string, tools: Pick<AgentToolBinding, "mcp_server_id" | "tool_name">[]) =>
    request<{ ok: boolean; tools: AgentToolBinding[] }>(`/agents/${id}/tools`, {
      method: "PUT",
      body: JSON.stringify({ tools }),
    }),
  formatAgentInstructions: (id: string, instructions?: string) =>
    request<{ markdown: string }>(`/agents/${id}/format`, {
      method: "POST",
      body: JSON.stringify({ instructions }),
    }),

  agentRunStream: async (
    agentId: string,
    onEvent: (event: {
      type: string;
      message?: string;
      step_id?: string;
      status?: string;
      payload?: Record<string, unknown>;
    }) => void,
    data?: { extra_instructions?: string; backend?: string; model?: string; ollama_base_url?: string },
  ): Promise<AgentRunResult> => {
    const res = await fetch(`${BASE}/agents/${agentId}/run/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data ?? {}),
    });
    if (!res.ok) {
      const text = await res.text();
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (typeof body.detail === "string") throw new Error(body.detail);
      } catch (e) {
        if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
      }
      throw new Error(text || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: AgentRunResult | null = null;

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
          step_id?: string;
          status?: string;
          payload?: Record<string, unknown>;
        };
        onEvent(event);
        if (event.type === "result" && event.payload) {
          result = event.payload as unknown as AgentRunResult;
        }
        if (event.type === "error") throw new Error(event.message || "Agent run failed");
      }
    }

    if (!result) throw new Error("Agent run finished without a result");
    return result;
  },

  listAgentFlows: () => request<AgentFlow[]>("/agent-flows"),
  getAgentFlow: (id: string) => request<AgentFlow>(`/agent-flows/${id}`),
  createAgentFlow: (data: {
    name: string;
    description?: string;
    instructions?: string;
    steps?: AgentFlow["steps"];
  }) => request<AgentFlow>("/agent-flows", { method: "POST", body: JSON.stringify(data) }),
  updateAgentFlow: (id: string, data: Partial<AgentFlow>) =>
    request<AgentFlow>(`/agent-flows/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAgentFlow: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/agent-flows/${id}`, { method: "DELETE" }),

  agentFlowRunStream: async (
    flowId: string,
    onEvent: (event: {
      type: string;
      message?: string;
      step_id?: string;
      status?: string;
      payload?: Record<string, unknown>;
    }) => void,
    data?: { extra_instructions?: string; backend?: string; model?: string; ollama_base_url?: string },
  ): Promise<AgentFlowRunResult> => {
    const res = await fetch(`${BASE}/agent-flows/${flowId}/run/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data ?? {}),
    });
    if (!res.ok) {
      const text = await res.text();
      try {
        const body = JSON.parse(text) as { detail?: string };
        if (typeof body.detail === "string") throw new Error(body.detail);
      } catch (e) {
        if (e instanceof Error && e.message !== text && !(e instanceof SyntaxError)) throw e;
      }
      throw new Error(text || res.statusText);
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let result: AgentFlowRunResult | null = null;

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
          step_id?: string;
          status?: string;
          payload?: Record<string, unknown>;
        };
        onEvent(event);
        if (event.type === "result" && event.payload) {
          result = event.payload as unknown as AgentFlowRunResult;
        }
        if (event.type === "error") throw new Error(event.message || "Agent flow run failed");
      }
    }

    if (!result) throw new Error("Agent flow run finished without a result");
    return result;
  },

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

  trinoServiceStatus: () => request<TrinoServiceStatusResponse>("/trino-service/status"),

  trinoServiceStart: () =>
    request<TrinoServiceActionResponse>("/trino-service/start", { method: "POST" }),

  trinoServiceStop: () =>
    request<TrinoServiceActionResponse>("/trino-service/stop", { method: "POST" }),

  trinoServiceRestart: () =>
    request<TrinoServiceActionResponse>("/trino-service/restart", { method: "POST" }),

  trinoServiceLog: (lines = 80) => request<{ log: string }>(`/trino-service/log?lines=${lines}`),

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

  previewMcpPrompt: (
    name: string,
    options?: { arguments?: Record<string, string>; domainId?: string },
  ) =>
    request<McpPromptPreviewResponse>(`/mcp/prompts/${encodeURIComponent(name)}/preview`, {
      method: "POST",
      body: JSON.stringify({
        arguments: options?.arguments ?? {},
        domain_id: options?.domainId ?? null,
      }),
    }),

  mcpPromptMeta: (name: string, domainId?: string) => {
    const q = domainId ? `?domain_id=${encodeURIComponent(domainId)}` : "";
    return request<McpPromptMetaResponse>(`/mcp/prompts/${encodeURIComponent(name)}/meta${q}`);
  },

  mcpToolDetail: (name: string) =>
    request<McpToolDetailResponse>(`/mcp/tools/${encodeURIComponent(name)}`),

  mcpResourceMeta: (uri: string) =>
    request<McpResourceMetaResponse>(`/mcp/resources/meta?uri=${encodeURIComponent(uri)}`),

  previewMcpResource: (
    uri: string,
    params?: Record<string, string>,
    domainId?: string,
  ) =>
    request<McpResourcePreviewResponse>("/mcp/resources/preview", {
      method: "POST",
      body: JSON.stringify({ uri, params: params ?? {}, domain_id: domainId ?? null }),
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
    trino?: TrinoSettingsPayload;
    mcp_url?: string;
    embedding_model?: string;
    ask?: { conversation_turns?: number };
    llm?: LlmSettingsPayload;
    mistral_api_key?: string;
  }) => request<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(data) }),
  testDatabase: (database: DatabaseSettingsPayload) =>
    request<{ ok: boolean; message: string }>("/settings/test-database", {
      method: "POST",
      body: JSON.stringify({ database }),
    }),
  metadataRagStatus: () => request<import("../types").MetadataRagStatus>("/settings/metadata-rag-status"),
  reRagMetadata: (embedding_model?: string) =>
    request<{
      updated: number;
      summary: string;
      status: import("../types").MetadataRagStatus;
    }>("/settings/re-rag", {
      method: "POST",
      body: JSON.stringify({ embedding_model }),
    }),

  listDbConnections: () => request<SavedDbConnection[]>("/connections"),
  listWarehouseConnectors: () => request<WarehouseConnectorDefinition[]>("/connections/warehouse-connectors"),
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
  testDbConnectionById: (id: string) =>
    request<{ ok: boolean; message: string }>(`/connections/${id}/test`, { method: "POST" }),
  getTrinoSettings: () =>
    request<TrinoSettingsPublic>("/connections/trino-settings"),
  testTrinoServer: (data: TrinoSettingsPayload) =>
    request<{ ok: boolean; message: string }>("/connections/trino-settings/test", {
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

export interface WarehouseConnectorField {
  id: string;
  label: string;
  type: "text" | "number" | "password" | "select";
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
}

export interface WarehouseConnectorDefinition {
  id: string;
  label: string;
  group: string;
  description: string;
  default_port: number;
  default_database: string;
  default_schema: string;
  fields: WarehouseConnectorField[];
}

export interface DbConnectionPayload {
  name: string;
  connector: string;
  warehouse_type: string;
  catalog: string;
  schema: string;
  host?: string;
  port?: number;
  user?: string;
  password?: string;
  database?: string;
  sslmode?: string;
  encrypt?: string;
  oracle_connect_mode?: string;
  oracle_service?: string;
  snowflake_account?: string;
  snowflake_warehouse?: string;
  snowflake_role?: string;
  trino_connector_name?: string;
  connection_url?: string;
  extra?: Record<string, string>;
}

export interface SavedDbConnection {
  id: string;
  name: string;
  connector: string;
  warehouse_type: string;
  warehouse_type_label: string;
  catalog: string;
  schema: string;
  host: string;
  port: number;
  user: string;
  database: string;
  password_set: boolean;
  sslmode?: string;
  encrypt?: string;
  oracle_connect_mode?: string;
  oracle_service?: string;
  snowflake_account?: string;
  snowflake_warehouse?: string;
  snowflake_role?: string;
  trino_connector_name?: string;
  connection_url?: string;
  extra?: Record<string, string>;
}

export interface TrinoSettingsPublic {
  host: string;
  port: number;
  user: string;
  http_scheme: string;
  verify_ssl: boolean;
  password_set: boolean;
}

export interface TrinoSettingsPayload {
  host: string;
  port: number;
  user: string;
  password?: string;
  http_scheme: string;
  verify_ssl: boolean;
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
  capability_name?: string;
  enabled: boolean;
  description?: string;
  uri?: string;
  mcp_server_id?: string;
  server_name?: string;
  server_slug?: string;
  server_url?: string;
  server_kind?: string;
  prompt_kind?: "global" | "local";
  local_slug?: string;
  local_prompt_id?: string;
}

export interface DomainPrompt {
  id: string;
  domain_id?: string;
  slug: string;
  name: string;
  description: string;
  template: string;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
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

export interface McpPromptMetaResponse {
  name: string;
  description: string;
  parameters: string[];
  domain_context: boolean;
  domain_filled_parameters: string[];
  enabled: boolean;
  prompt_kind?: "global" | "local";
  local_slug?: string;
  local_prompt_id?: string;
}

export interface McpPromptPreviewResponse {
  preview: string;
  arguments: Record<string, string>;
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

export interface TrinoServiceStatusResponse {
  url: string;
  info_url: string;
  host: string;
  port: number;
  reachable: boolean;
  running: boolean;
  container_running: boolean;
  status_label: string;
  container_id: string | null;
  container_name: string;
  source: string;
  docker_available: boolean;
  log_path: string;
  managed: boolean;
}

export interface TrinoServiceActionResponse extends TrinoServiceStatusResponse {
  ok: boolean;
  message: string;
}

export interface LlmModelOption {
  id: string;
  label: string;
  hint?: string;
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
  mistral_model_options: LlmModelOption[];
  llm: LlmSettingsPublic;
  mistral_api_key_set: boolean;
  ask: {
    conversation_turns: number;
    max_conversation_turns: number;
  };
  trino?: TrinoSettingsPublic;
}
