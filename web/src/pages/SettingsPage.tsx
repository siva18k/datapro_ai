import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { PageHeader } from "../components/PageHeader";
import { SavedConnectionsPanel } from "../components/SavedConnectionsPanel";
import { useApiConnection } from "../context/ApiConnectionContext";
import { api, type DatabaseSettingsPayload, type LlmSettingsPayload } from "../api/client";

const LLM_KEY_BACKENDS = ["mistral", "openai", "anthropic", "gemini", "openrouter"] as const;
type LlmKeyBackend = (typeof LLM_KEY_BACKENDS)[number];

const LLM_KEY_LABELS: Record<LlmKeyBackend, string> = {
  mistral: "Mistral API key",
  openai: "OpenAI API key",
  anthropic: "Claude (Anthropic) API key",
  gemini: "Gemini API key",
  openrouter: "OpenRouter API key",
};

const emptyDb = (): DatabaseSettingsPayload => ({
  use_database_url: false,
  database_url: "",
  host: "",
  port: 5432,
  user: "",
  password: "",
  database: "",
  schema: "ragpro",
  sslmode: "require",
});

export function SettingsPage() {
  const qc = useQueryClient();
  const { apiOnline, checking: apiChecking } = useApiConnection();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
    enabled: apiOnline,
  });

  const [db, setDb] = useState<DatabaseSettingsPayload>(emptyDb);
  const [mcpUrl, setMcpUrl] = useState("http://127.0.0.1:8000/mcp");
  const [embeddingModel, setEmbeddingModel] = useState("all-MiniLM-L6-v2");
  const [llm, setLlm] = useState<LlmSettingsPayload>({
    default_backend: "mistral",
    default_model: "",
    ollama_base_url: "http://localhost:11434",
  });
  const [apiKeys, setApiKeys] = useState({
    mistral: "",
    openai: "",
    anthropic: "",
    gemini: "",
    openrouter: "",
  });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mcpNotice, setMcpNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: mcpStatus, refetch: refetchMcpStatus } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    enabled: apiOnline,
    refetchInterval: apiOnline ? 10_000 : false,
  });

  const mcpIsRunning = Boolean(
    mcpStatus?.reachable || (mcpStatus?.listener_pids?.length ?? 0) > 0,
  );

  const invalidateMcpStatus = () => {
    void refetchMcpStatus();
    void qc.invalidateQueries({ queryKey: ["mcp"] });
  };

  const mcpStart = useMutation({
    mutationFn: api.mcpStart,
    onSuccess: (res) => {
      invalidateMcpStatus();
      setMcpNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setMcpNotice({ ok: false, text: String(err) }),
  });

  const mcpStop = useMutation({
    mutationFn: api.mcpStop,
    onSuccess: (res) => {
      invalidateMcpStatus();
      setMcpNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setMcpNotice({ ok: false, text: String(err) }),
  });

  const mcpRestart = useMutation({
    mutationFn: api.mcpRestart,
    onSuccess: (res) => {
      invalidateMcpStatus();
      setMcpNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setMcpNotice({ ok: false, text: String(err) }),
  });

  const mcpBusy = mcpStart.isPending || mcpStop.isPending || mcpRestart.isPending;

  const [backendNotice, setBackendNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: backendStatus, refetch: refetchBackendStatus } = useQuery({
    queryKey: ["backend", "status"],
    queryFn: api.backendStatus,
    enabled: apiOnline,
    refetchInterval: apiOnline ? 10_000 : false,
  });

  const backendIsRunning = Boolean(
    backendStatus?.reachable || (backendStatus?.listener_pids?.length ?? 0) > 0,
  );

  const invalidateBackendStatus = () => {
    void refetchBackendStatus();
    void qc.invalidateQueries({ queryKey: ["backend"] });
  };

  const backendStart = useMutation({
    mutationFn: api.backendStart,
    onSuccess: (res) => {
      invalidateBackendStatus();
      setBackendNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setBackendNotice({ ok: false, text: String(err) }),
  });

  const backendStop = useMutation({
    mutationFn: api.backendStop,
    onSuccess: (res) => {
      invalidateBackendStatus();
      setBackendNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setBackendNotice({ ok: false, text: String(err) }),
  });

  const backendRestart = useMutation({
    mutationFn: api.backendRestart,
    onSuccess: (res) => {
      invalidateBackendStatus();
      setBackendNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setBackendNotice({ ok: false, text: String(err) }),
  });

  const backendBusy = backendStart.isPending || backendStop.isPending || backendRestart.isPending;

  useEffect(() => {
    if (!data) return;
    setDb({
      use_database_url: data.database.use_database_url,
      database_url: data.database.database_url === "***" ? "" : data.database.database_url,
      host: data.database.host,
      port: data.database.port,
      user: data.database.user,
      database: data.database.database,
      schema: data.database.schema,
      sslmode: data.database.sslmode,
      password: "",
    });
    setMcpUrl(data.mcp_url);
    setEmbeddingModel(data.embedding_model);
    setLlm({
      default_backend: data.llm.default_backend,
      default_model: data.llm.default_model,
      ollama_base_url: data.llm.ollama_base_url,
    });
    setApiKeys({ mistral: "", openai: "", anthropic: "", gemini: "", openrouter: "" });
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      api.saveSettings({
        database: {
          ...db,
          password: db.password || undefined,
        },
        mcp_url: mcpUrl,
        embedding_model: embeddingModel,
        llm: {
          ...llm,
          mistral_api_key: apiKeys.mistral || undefined,
          openai_api_key: apiKeys.openai || undefined,
          anthropic_api_key: apiKeys.anthropic || undefined,
          gemini_api_key: apiKeys.gemini || undefined,
          openrouter_api_key: apiKeys.openrouter || undefined,
        },
      }),
    onSuccess: (res) => {
      qc.setQueryData(["settings"], res);
      setApiKeys({ mistral: "", openai: "", anthropic: "", gemini: "", openrouter: "" });
      setDb((prev) => ({ ...prev, password: "" }));
      setMessage("Settings saved to .env and applied for this API server.");
      setError(null);
    },
    onError: (err) => {
      setError(String(err));
      setMessage(null);
    },
  });

  const testDb = useMutation({
    mutationFn: () =>
      api.testDatabase({
        ...db,
        password: db.password || undefined,
      }),
    onSuccess: (res) => {
      setMessage(res.message);
      setError(null);
    },
    onError: (err) => {
      setError(String(err));
      setMessage(null);
    },
  });

  const updateDb = (patch: Partial<DatabaseSettingsPayload>) => setDb((prev) => ({ ...prev, ...patch }));

  const selectedBackend = llm.default_backend ?? "mistral";
  const selectedBackendMeta = data?.llm_backends.find((b) => b.id === selectedBackend);
  const needsApiKey = LLM_KEY_BACKENDS.includes(selectedBackend as LlmKeyBackend);
  const apiKeySet = needsApiKey
    ? data?.llm[`${selectedBackend}_api_key_set` as `${LlmKeyBackend}_api_key_set`]
    : false;

  return (
    <div className="max-w-6xl space-y-4">
      <PageHeader
        title="Settings"
        description="Database, models, and servers"
      />

      {apiChecking && !apiOnline && <p className="text-sm text-zinc-500">Connecting to API server…</p>}

      {!apiOnline && !apiChecking && <ApiOfflinePanel title="Start the API server" />}

      {apiOnline && isLoading && <p className="text-sm text-zinc-500">Loading settings…</p>}

      {apiOnline && data && (
        <>
          <div className="settings-db-split">
            <div className="card card-pad space-y-4">
              <div>
                <h2 className="font-semibold">Catalog database</h2>
                <p className="mt-1 text-sm text-zinc-500">Postgres for catalog &amp; RAG</p>
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={db.use_database_url}
                  onChange={(e) => updateDb({ use_database_url: e.target.checked })}
                />
                Use DATABASE_URL instead of separate fields
              </label>

              {db.use_database_url ? (
                <div className="field mb-0">
                  <label className="label">DATABASE_URL</label>
                  <input
                    className="input font-mono text-xs"
                    placeholder={
                      data.database.database_url === "***" ? "Leave blank to keep current URL" : "postgresql://..."
                    }
                    value={db.database_url}
                    onChange={(e) => updateDb({ database_url: e.target.value })}
                  />
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="field mb-0 sm:col-span-2">
                    <label className="label">Host</label>
                    <input className="input" value={db.host} onChange={(e) => updateDb({ host: e.target.value })} />
                  </div>
                  <div className="field mb-0">
                    <label className="label">Port</label>
                    <input
                      className="input"
                      type="number"
                      value={db.port}
                      onChange={(e) => updateDb({ port: Number(e.target.value) })}
                    />
                  </div>
                  <div className="field mb-0">
                    <label className="label">SSL mode</label>
                    <select className="select" value={db.sslmode} onChange={(e) => updateDb({ sslmode: e.target.value })}>
                      <option value="require">require</option>
                      <option value="verify-full">verify-full</option>
                      <option value="prefer">prefer</option>
                      <option value="disable">disable</option>
                    </select>
                  </div>
                  <div className="field mb-0">
                    <label className="label">User</label>
                    <input className="input" value={db.user} onChange={(e) => updateDb({ user: e.target.value })} />
                  </div>
                  <div className="field mb-0">
                    <label className="label">Password</label>
                    <input
                      className="input"
                      type="password"
                      placeholder={data.database.password_set ? "Leave blank to keep current password" : ""}
                      value={db.password}
                      onChange={(e) => updateDb({ password: e.target.value })}
                    />
                  </div>
                  <div className="field mb-0">
                    <label className="label">Database</label>
                    <input className="input" value={db.database} onChange={(e) => updateDb({ database: e.target.value })} />
                  </div>
                  <div className="field mb-0">
                    <label className="label">Schema</label>
                    <input className="input" value={db.schema} onChange={(e) => updateDb({ schema: e.target.value })} />
                  </div>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={testDb.isPending}
                  onClick={() => testDb.mutate()}
                >
                  {testDb.isPending ? "Testing…" : "Test catalog connection"}
                </button>
              </div>
            </div>

            <div className="card card-pad">
              <SavedConnectionsPanel />
            </div>
          </div>

          <div className="card card-pad">
            <div className="grid gap-6 md:grid-cols-2 md:gap-8">
              <div className="space-y-4">
                <div>
                  <h2 className="font-semibold">LLM</h2>
                  <p className="mt-1 text-sm text-zinc-500">Default for Ask &amp; Analytics</p>
                </div>
                <div className="field mb-0">
                  <label className="label">Provider</label>
                  <select
                    className="select"
                    value={selectedBackend}
                    onChange={(e) => {
                      const id = e.target.value;
                      const backend = data.llm_backends.find((b) => b.id === id);
                      setLlm((prev) => ({
                        ...prev,
                        default_backend: id,
                        default_model: backend?.default_model ?? prev.default_model,
                      }));
                    }}
                  >
                    {data.llm_backends.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field mb-0">
                  <label className="label">Model (optional override)</label>
                  <input
                    className="input font-mono text-xs"
                    placeholder={selectedBackendMeta?.default_model ?? "Provider default"}
                    value={llm.default_model ?? ""}
                    onChange={(e) => setLlm((prev) => ({ ...prev, default_model: e.target.value }))}
                  />
                </div>
                {needsApiKey && (
                  <div className="field mb-0">
                    <label className="label">{LLM_KEY_LABELS[selectedBackend as LlmKeyBackend]}</label>
                    <input
                      className="input font-mono text-xs"
                      type="password"
                      placeholder={apiKeySet ? "Leave blank to keep current key" : "API key"}
                      value={apiKeys[selectedBackend as LlmKeyBackend]}
                      onChange={(e) =>
                        setApiKeys((prev) => ({ ...prev, [selectedBackend as LlmKeyBackend]: e.target.value }))
                      }
                    />
                  </div>
                )}
                {selectedBackend === "ollama" && (
                  <div className="field mb-0">
                    <label className="label">Ollama base URL</label>
                    <input
                      className="input font-mono text-xs"
                      value={llm.ollama_base_url ?? "http://localhost:11434"}
                      onChange={(e) => setLlm((prev) => ({ ...prev, ollama_base_url: e.target.value }))}
                    />
                  </div>
                )}
              </div>

              <div className="space-y-4 md:border-l md:border-zinc-200 md:pl-8">
                <div>
                  <h2 className="font-semibold">Embedding model</h2>
                  <p className="mt-1 text-sm text-zinc-500">Global — re-ingest after change</p>
                </div>
                <div className="field mb-0">
                  <label className="label">Model</label>
                  <select
                    className="select"
                    value={embeddingModel}
                    onChange={(e) => setEmbeddingModel(e.target.value)}
                  >
                    {data.embedding_model_options.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="card card-pad">
            <div className="grid gap-6 md:grid-cols-2 md:gap-8">
              <div className="space-y-4">
                <div>
                  <h2 className="font-semibold">MCP server</h2>
                  <p className="mt-1 text-sm text-zinc-500">Local MCP process</p>
                </div>

                {mcpStatus && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`badge ${mcpStatus.reachable ? "badge-ok" : "badge-muted"}`}>
                      {mcpStatus.reachable ? "Reachable" : "Stopped"}
                    </span>
                    <span className="badge-muted badge">{mcpStatus.status_label}</span>
                    {mcpStatus.active_pid != null && (
                      <span className="badge-muted badge">PID {mcpStatus.active_pid}</span>
                    )}
                  </div>
                )}

                <div className="field mb-0">
                  <label className="label">MCP URL</label>
                  <input className="input font-mono text-xs" value={mcpUrl} onChange={(e) => setMcpUrl(e.target.value)} />
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={mcpBusy || mcpIsRunning}
                    onClick={() => mcpStart.mutate()}
                  >
                    {mcpStart.isPending ? "Starting…" : "Start"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={mcpBusy || !mcpIsRunning}
                    onClick={() => mcpStop.mutate()}
                  >
                    {mcpStop.isPending ? "Stopping…" : "Stop"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={mcpBusy || !mcpIsRunning}
                    onClick={() => mcpRestart.mutate()}
                  >
                    {mcpRestart.isPending ? "Restarting…" : "Restart"}
                  </button>
                </div>

                {mcpStatus?.source === "external" && (
                  <p className="text-xs text-zinc-500">External process — Stop kills port {mcpStatus.port}.</p>
                )}

                {mcpNotice && (
                  <p className={mcpNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{mcpNotice.text}</p>
                )}
              </div>

              <div className="space-y-4 md:border-l md:border-zinc-200 md:pl-8">
                <div>
                  <h2 className="font-semibold">API server</h2>
                  <p className="mt-1 text-sm text-zinc-500">FastAPI backend</p>
                </div>

                {backendStatus && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`badge ${backendStatus.reachable ? "badge-ok" : "badge-muted"}`}>
                      {backendStatus.reachable ? "Reachable" : "Stopped"}
                    </span>
                    <span className="badge-muted badge">{backendStatus.status_label}</span>
                    {backendStatus.active_pid != null && (
                      <span className="badge-muted badge">PID {backendStatus.active_pid}</span>
                    )}
                    <span className="badge-muted badge">Port {backendStatus.port}</span>
                  </div>
                )}

                {backendStatus && (
                  <p className="text-sm">
                    URL:{" "}
                    <code className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs">{backendStatus.url}</code>
                  </p>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={backendBusy || backendIsRunning}
                    onClick={() => backendStart.mutate()}
                  >
                    {backendStart.isPending ? "Starting…" : "Start"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={backendBusy || !backendIsRunning}
                    onClick={() => backendStop.mutate()}
                  >
                    {backendStop.isPending ? "Stopping…" : "Stop"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={backendBusy || !backendIsRunning}
                    onClick={() => backendRestart.mutate()}
                  >
                    {backendRestart.isPending ? "Restarting…" : "Restart"}
                  </button>
                </div>

                {backendStatus?.stopping_self && backendIsRunning && (
                  <p className="text-xs text-zinc-500">Restart may disconnect this page briefly.</p>
                )}

                {backendNotice && (
                  <p className={backendNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{backendNotice.text}</p>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save catalog & service settings"}
            </button>
            <p className="text-xs text-zinc-500">Writes to {data.env_path}. Restart API or MCP after changes.</p>
          </div>

          {message && <p className="alert-ok">{message}</p>}
          {error && <p className="alert-error">{error}</p>}
        </>
      )}
    </div>
  );
}
