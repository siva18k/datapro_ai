import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiConnectingPanel } from "../components/ApiConnectingPanel";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { CatalogDatabaseCard } from "../components/CatalogDatabaseCard";
import { PageHeader } from "../components/PageHeader";
import { SavedConnectionsPanel } from "../components/SavedConnectionsPanel";
import { useApiPageState } from "../context/ApiConnectionContext";
import {
  api,
  type BackendActionResponse,
  type BackendStatusResponse,
  type DatabaseSettingsPayload,
  type LlmSettingsPayload,
  type TrinoSettingsPayload,
} from "../api/client";
import { devBootstrap, isDevBootstrapAvailable } from "../api/devBootstrap";
import { parsePostgresUrl } from "../utils/postgresUrl";

const MISTRAL_CUSTOM_MODEL = "__custom__";
const LLM_KEY_BACKENDS = ["mistral", "openai", "anthropic", "gemini", "openrouter"] as const;
type LlmKeyBackend = (typeof LLM_KEY_BACKENDS)[number];

const LLM_KEY_LABELS: Record<LlmKeyBackend, string> = {
  mistral: "Mistral API key",
  openai: "OpenAI API key",
  anthropic: "Claude (Anthropic) API key",
  gemini: "Gemini API key",
  openrouter: "OpenRouter API key",
};

function sanitizeModelOverride(value: string | undefined): string {
  const cleaned = (value ?? "").trim();
  if (!cleaned || cleaned.includes("@")) {
    return "";
  }
  return cleaned;
}

function setModelOverride(value: string): string {
  return sanitizeModelOverride(value);
}

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

function isCatalogConfigured(
  db: DatabaseSettingsPayload,
  databaseUrlSet: boolean,
): boolean {
  if (db.host.trim() && db.user.trim() && db.database.trim()) {
    return true;
  }
  if (db.use_database_url) {
    return databaseUrlSet || db.database_url.trim().length > 0;
  }
  return false;
}

function buildDatabasePayload(
  db: DatabaseSettingsPayload,
  options: { password?: string; preserveUrl?: boolean; urlConfigured?: boolean },
): DatabaseSettingsPayload {
  const usingUrl = Boolean(options.preserveUrl && (db.use_database_url || options.urlConfigured));
  if (usingUrl) {
    return {
      ...db,
      use_database_url: true,
      database_url: db.database_url?.trim() || "***",
      password: options.password || undefined,
    };
  }
  return {
    ...db,
    use_database_url: false,
    database_url: "",
    password: options.password || undefined,
  };
}

const emptyTrino = (): TrinoSettingsPayload => ({
  host: "localhost",
  port: 8081,
  user: "trino",
  http_scheme: "http",
  verify_ssl: false,
});

export function SettingsPage() {
  const qc = useQueryClient();
  const { apiOnline, showConnecting, showOffline, connectingTitle } = useApiPageState();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
    enabled: apiOnline,
  });

  const [db, setDb] = useState<DatabaseSettingsPayload>(emptyDb);
  const [mcpUrl, setMcpUrl] = useState("http://127.0.0.1:8000/mcp");
  const [embeddingModel, setEmbeddingModel] = useState("all-MiniLM-L6-v2");
  const [conversationTurns, setConversationTurns] = useState(5);
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
  const [mistralCustomMode, setMistralCustomMode] = useState(false);
  const [catalogEditing, setCatalogEditing] = useState(true);
  const [catalogUrlPaste, setCatalogUrlPaste] = useState("");
  const [catalogUrlPasteError, setCatalogUrlPasteError] = useState<string | null>(null);
  const [catalogDbNotice, setCatalogDbNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [trino, setTrino] = useState<TrinoSettingsPayload>(emptyTrino());
  const [trinoPassword, setTrinoPassword] = useState("");
  const [trinoEditing, setTrinoEditing] = useState(false);
  const [trinoNotice, setTrinoNotice] = useState<{ ok: boolean; text: string } | null>(null);
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
    mutationFn: async (): Promise<BackendActionResponse> => {
      if (isDevBootstrapAvailable()) {
        const dev = await devBootstrap.stopApi();
        if (dev.ok || !dev.reachable) {
          try {
            const status = await api.backendStatus();
            return { ...status, ok: dev.ok, message: dev.message };
          } catch {
            const fallback: BackendStatusResponse = {
              url: dev.url,
              health_url: `${dev.url}/api/health`,
              host: "127.0.0.1",
              port: dev.port,
              reachable: dev.reachable,
              running: dev.reachable,
              source: dev.reachable ? "unknown" : "stopped",
              status_label: dev.reachable ? "Running (reachable, process not identified on port)" : "Stopped",
              active_pid: null,
              listener_pids: [],
              stopping_self: false,
              log_path: "",
            };
            return { ...fallback, ok: dev.ok, message: dev.message };
          }
        }
      }
      return api.backendStop();
    },
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

  const [trinoServiceNotice, setTrinoServiceNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: trinoServiceStatus, refetch: refetchTrinoServiceStatus } = useQuery({
    queryKey: ["trino-service", "status"],
    queryFn: api.trinoServiceStatus,
    enabled: apiOnline,
    refetchInterval: apiOnline ? 10_000 : false,
  });

  const trinoServiceIsRunning = Boolean(
    trinoServiceStatus?.reachable || trinoServiceStatus?.container_running,
  );

  const invalidateTrinoServiceStatus = () => {
    void refetchTrinoServiceStatus();
    void qc.invalidateQueries({ queryKey: ["trino-service"] });
  };

  const trinoServiceStart = useMutation({
    mutationFn: api.trinoServiceStart,
    onSuccess: (res) => {
      invalidateTrinoServiceStatus();
      setTrinoServiceNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setTrinoServiceNotice({ ok: false, text: String(err) }),
  });

  const trinoServiceStop = useMutation({
    mutationFn: api.trinoServiceStop,
    onSuccess: (res) => {
      invalidateTrinoServiceStatus();
      setTrinoServiceNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setTrinoServiceNotice({ ok: false, text: String(err) }),
  });

  const trinoServiceRestart = useMutation({
    mutationFn: api.trinoServiceRestart,
    onSuccess: (res) => {
      invalidateTrinoServiceStatus();
      setTrinoServiceNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setTrinoServiceNotice({ ok: false, text: String(err) }),
  });

  const trinoServiceBusy =
    trinoServiceStart.isPending || trinoServiceStop.isPending || trinoServiceRestart.isPending;

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
    setConversationTurns(data.ask?.conversation_turns ?? 5);
    setLlm({
      default_backend: data.llm.default_backend,
      default_model: sanitizeModelOverride(data.llm.default_model),
      ollama_base_url: data.llm.ollama_base_url,
    });
    const model = sanitizeModelOverride(data.llm.default_model);
    const knownMistralIds = new Set((data.mistral_model_options ?? []).map((option) => option.id));
    setMistralCustomMode(
      data.llm.default_backend === "mistral" && model !== "" && !knownMistralIds.has(model),
    );
    setApiKeys({ mistral: "", openai: "", anthropic: "", gemini: "", openrouter: "" });
    setTrino({
      host: data.trino?.host || "localhost",
      port: data.trino?.port ?? 8081,
      user: data.trino?.user || "trino",
      http_scheme: data.trino?.http_scheme || "http",
      verify_ssl: data.trino?.verify_ssl ?? false,
    });
    setTrinoPassword("");
    setTrinoEditing(!Boolean((data.trino?.host || "").trim()));
    setCatalogEditing(
      !isCatalogConfigured(
        {
          use_database_url: data.database.use_database_url,
          database_url: data.database.database_url === "***" ? "" : data.database.database_url,
          host: data.database.host,
          port: data.database.port,
          user: data.database.user,
          password: "",
          database: data.database.database,
          schema: data.database.schema,
          sslmode: data.database.sslmode,
        },
        data.database.database_url === "***",
      ),
    );
  }, [data]);

  const save = useMutation({
    mutationFn: () => {
      const keyPayload: Record<string, string> = {};
      for (const backend of LLM_KEY_BACKENDS) {
        const value = apiKeys[backend].trim();
        if (value.length >= 20) {
          keyPayload[`${backend}_api_key`] = value;
        }
      }
      return api.saveSettings({
        database: buildDatabasePayload(db, {
          password: db.password || undefined,
          preserveUrl: !catalogEditing,
          urlConfigured: data?.database.database_url === "***",
        }),
        trino: {
          ...trino,
          password: trinoPassword || undefined,
        },
        mcp_url: mcpUrl,
        embedding_model: embeddingModel,
        ask: { conversation_turns: conversationTurns },
        llm: {
          ...llm,
          default_model: sanitizeModelOverride(llm.default_model),
          ...keyPayload,
        },
      });
    },
    onSuccess: (res) => {
      qc.setQueryData(["settings"], res);
      setApiKeys({ mistral: "", openai: "", anthropic: "", gemini: "", openrouter: "" });
      setDb((prev) => ({ ...prev, password: "" }));
      setTrinoPassword("");
      setTrinoEditing(false);
      setCatalogEditing(false);
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
      api.testDatabase(
        buildDatabasePayload(db, {
          password: db.password || undefined,
          preserveUrl: true,
          urlConfigured: data?.database.database_url === "***",
        }),
      ),
    onMutate: () => {
      setCatalogDbNotice(null);
      setError(null);
    },
    onSuccess: (res) => {
      setCatalogDbNotice({ ok: true, text: res.message });
      setMessage(null);
      setError(null);
    },
    onError: (err) => {
      setCatalogDbNotice({ ok: false, text: String(err) });
      setMessage(null);
    },
  });

  const updateDb = (patch: Partial<DatabaseSettingsPayload>) => setDb((prev) => ({ ...prev, ...patch }));

  const openCatalogEdit = () => {
    setDb((prev) => ({ ...prev, use_database_url: false, database_url: "" }));
    setCatalogUrlPaste("");
    setCatalogUrlPasteError(null);
    setCatalogEditing(true);
  };

  const applyCatalogUrlPaste = () => {
    const parsed = parsePostgresUrl(catalogUrlPaste);
    if (!parsed) {
      setCatalogUrlPasteError("Could not parse connection URL. Use postgresql://user:pass@host:5432/database");
      return;
    }
    setCatalogUrlPasteError(null);
    setDb((prev) => ({
      ...prev,
      ...parsed,
      schema: prev.schema || "ragpro",
      password: parsed.password ?? prev.password,
    }));
  };

  const resetCatalogFromData = () => {
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
    setCatalogUrlPaste("");
    setCatalogUrlPasteError(null);
  };

  const resetTrinoFromData = () => {
    if (!data?.trino) return;
    setTrino({
      host: data.trino.host || "localhost",
      port: data.trino.port ?? 8081,
      user: data.trino.user || "trino",
      http_scheme: data.trino.http_scheme || "http",
      verify_ssl: data.trino.verify_ssl ?? false,
    });
    setTrinoPassword("");
    setTrinoNotice(null);
  };

  const catalogConfigured = isCatalogConfigured(db, data?.database.database_url === "***");
  const catalogUsesUrl =
    db.use_database_url && (data?.database.database_url === "***" || Boolean(db.database_url.trim()));
  const catalogUserFallback = catalogUsesUrl ? "Configured via URL" : undefined;

  const selectedBackend = llm.default_backend ?? "mistral";
  const selectedBackendMeta = data?.llm_backends.find((b) => b.id === selectedBackend);
  const mistralModelOptions = data?.mistral_model_options ?? [];
  const mistralProviderDefault = selectedBackendMeta?.default_model ?? "codestral-2508";
  const mistralModelValue = llm.default_model ?? "";
  const mistralSelectValue = mistralCustomMode
    ? MISTRAL_CUSTOM_MODEL
    : mistralModelValue || mistralProviderDefault;
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

      {showConnecting && <ApiConnectingPanel title={connectingTitle} />}

      {showOffline && <ApiOfflinePanel title="Start the API server" />}

      {apiOnline && isLoading && <p className="text-sm text-zinc-500">Loading settings…</p>}

      {apiOnline && data && (
        <>
          <div className="card card-pad">
            <SavedConnectionsPanel
              catalog={
                <CatalogDatabaseCard
                  db={db}
                  passwordSet={data.database.password_set}
                  configured={catalogConfigured}
                  editing={catalogEditing}
                  userFallback={catalogUserFallback}
                  urlPaste={catalogUrlPaste}
                  urlPasteError={catalogUrlPasteError}
                  notice={catalogDbNotice}
                  testing={testDb.isPending}
                  onEdit={openCatalogEdit}
                  onCancel={() => {
                    resetCatalogFromData();
                    setCatalogEditing(false);
                  }}
                  onUpdateDb={updateDb}
                  onUrlPasteChange={(value) => {
                    setCatalogUrlPaste(value);
                    setCatalogUrlPasteError(null);
                  }}
                  onApplyUrlPaste={applyCatalogUrlPaste}
                  onTest={() => testDb.mutate()}
                />
              }
              trino={trino}
              trinoPassword={trinoPassword}
              trinoEditing={trinoEditing}
              trinoNotice={trinoNotice}
              onTrinoEdit={() => {
                setTrinoNotice(null);
                setTrinoEditing(true);
              }}
              onTrinoCancel={() => {
                resetTrinoFromData();
                setTrinoEditing(false);
              }}
              onTrinoChange={(patch) => setTrino((prev) => ({ ...prev, ...patch }))}
              onTrinoPasswordChange={setTrinoPassword}
              onTrinoNotice={setTrinoNotice}
            />
          </div>

          <div className="card card-pad space-y-4">
            <div>
              <h2 className="font-semibold">LLM</h2>
              <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
                Default for Ask &amp; Analytics
              </p>
            </div>
            <form className="settings-llm-grid" autoComplete="off" onSubmit={(e) => e.preventDefault()}>
              <div className="field mb-0">
                <label className="label" htmlFor="datapro-llm-provider">
                  Provider
                </label>
                <select
                  id="datapro-llm-provider"
                  className="select"
                  autoComplete="off"
                  value={selectedBackend}
                  onChange={(e) => {
                    const id = e.target.value;
                    const backend = data.llm_backends.find((b) => b.id === id);
                    setLlm((prev) => ({
                      ...prev,
                      default_backend: id,
                      default_model: sanitizeModelOverride(backend?.default_model ?? prev.default_model),
                    }));
                    setMistralCustomMode(false);
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
                <label className="label" htmlFor="datapro-llm-model-override">
                  Model
                </label>
                {selectedBackend === "mistral" ? (
                  <>
                    <select
                      id="datapro-llm-model-override"
                      className="select font-mono text-xs"
                      autoComplete="off"
                      value={mistralSelectValue}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value === MISTRAL_CUSTOM_MODEL) {
                          setMistralCustomMode(true);
                          return;
                        }
                        setMistralCustomMode(false);
                        setLlm((prev) => ({ ...prev, default_model: value }));
                      }}
                    >
                      {mistralModelOptions.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.label}
                          {option.hint ? ` — ${option.hint}` : ""}
                        </option>
                      ))}
                      <option value={MISTRAL_CUSTOM_MODEL}>Custom model ID…</option>
                    </select>
                    {mistralCustomMode && (
                      <input
                        className="input mt-2 font-mono text-xs"
                        name="datapro-llm-model-custom"
                        type="search"
                        autoComplete="off"
                        autoCorrect="off"
                        autoCapitalize="off"
                        spellCheck={false}
                        data-lpignore="true"
                        data-1p-ignore
                        data-form-type="other"
                        placeholder="e.g. mistral-medium-latest"
                        value={mistralModelValue}
                        onChange={(e) =>
                          setLlm((prev) => ({
                            ...prev,
                            default_model: setModelOverride(e.target.value),
                          }))
                        }
                      />
                    )}
                  </>
                ) : (
                  <input
                    id="datapro-llm-model-override"
                    className="input font-mono text-xs"
                    name="datapro-llm-model-override"
                    type="search"
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="off"
                    spellCheck={false}
                    data-lpignore="true"
                    data-1p-ignore
                    data-form-type="other"
                    readOnly
                    onFocus={(e) => e.currentTarget.removeAttribute("readonly")}
                    onBlur={(e) => {
                      e.currentTarget.setAttribute("readonly", "");
                      const cleaned = sanitizeModelOverride(e.currentTarget.value);
                      if (cleaned !== e.currentTarget.value) {
                        setLlm((prev) => ({ ...prev, default_model: cleaned }));
                      }
                    }}
                    placeholder={selectedBackendMeta?.default_model ?? "Provider default"}
                    value={llm.default_model ?? ""}
                    onChange={(e) =>
                      setLlm((prev) => ({ ...prev, default_model: setModelOverride(e.target.value) }))
                    }
                  />
                )}
              </div>
              {needsApiKey ? (
                <div className="field mb-0">
                  <label className="label">{LLM_KEY_LABELS[selectedBackend as LlmKeyBackend]}</label>
                  <input
                    className="input font-mono text-xs"
                    type="password"
                    autoComplete="new-password"
                    name={`datapro-${selectedBackend}-api-key`}
                    placeholder={apiKeySet ? "Leave blank to keep current key" : "API key"}
                    value={apiKeys[selectedBackend as LlmKeyBackend]}
                    onChange={(e) =>
                      setApiKeys((prev) => ({ ...prev, [selectedBackend as LlmKeyBackend]: e.target.value }))
                    }
                  />
                </div>
              ) : selectedBackend === "ollama" ? (
                <div className="field mb-0">
                  <label className="label">Ollama URL</label>
                  <input
                    className="input font-mono text-xs"
                    value={llm.ollama_base_url ?? "http://localhost:11434"}
                    onChange={(e) => setLlm((prev) => ({ ...prev, ollama_base_url: e.target.value }))}
                  />
                </div>
              ) : null}
              <div className="field mb-0">
                <label className="label" htmlFor="datapro-embedding-model">
                  Embedding model
                </label>
                <select
                  id="datapro-embedding-model"
                  className="select font-mono text-xs"
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
            </form>
            {selectedBackend === "mistral" ? (
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                Free tier rate limits apply per model.{" "}
                <code className="text-xs">codestral-2508</code> for SQL and code; Ministral 3B for fast Q&amp;A.
              </p>
            ) : (
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                Leave model blank to use the provider default.
              </p>
            )}
          </div>

          <div className="card card-pad">
            <div className="space-y-4">
              <div>
                <h2 className="font-semibold">Ask</h2>
                <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
                  Follow-up context for the chat prompt until you press New chat
                </p>
              </div>
              <div className="field mb-0 max-w-md">
                <label className="label" htmlFor="ask-conversation-turns">
                  Conversation turns to remember
                </label>
                <input
                  id="ask-conversation-turns"
                  type="number"
                  className="input"
                  min={0}
                  max={data.ask?.max_conversation_turns ?? 20}
                  value={conversationTurns}
                  onChange={(e) => setConversationTurns(Number(e.target.value))}
                />
                <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
                  Number of prior Q&amp;A exchanges included in each follow-up (0 = disabled). Cleared when you start a new chat.
                </p>
              </div>
            </div>
          </div>

          <div className="settings-servers-stack">
            <div className="card card-pad space-y-4">
              <div>
                <h2 className="font-semibold">MCP server</h2>
                <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
                  Local MCP process
                </p>
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
                <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                  External process — Stop kills port {mcpStatus.port}.
                </p>
              )}

              {mcpNotice && (
                <p className={mcpNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{mcpNotice.text}</p>
              )}
            </div>

            <div className="card card-pad space-y-4">
              <div>
                <h2 className="font-semibold">API server</h2>
                <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
                  FastAPI backend
                </p>
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
                  <code className="rounded px-1.5 py-0.5 text-xs" style={{ background: "var(--color-surface-subtle)" }}>
                    {backendStatus.url}
                  </code>
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
                <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                  Restart may disconnect this page briefly.
                </p>
              )}

              {backendNotice && (
                <p className={backendNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{backendNotice.text}</p>
              )}
            </div>

            <div className="card card-pad space-y-4">
              <div>
                <h2 className="font-semibold">Trino coordinator</h2>
                <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
                  Docker service for business warehouse SQL
                </p>
              </div>

              {trinoServiceStatus && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`badge ${trinoServiceStatus.reachable ? "badge-ok" : "badge-muted"}`}>
                    {trinoServiceStatus.reachable ? "Reachable" : "Stopped"}
                  </span>
                  <span className="badge-muted badge">{trinoServiceStatus.status_label}</span>
                  {trinoServiceStatus.container_id && (
                    <span className="badge-muted badge font-mono text-xs">
                      {trinoServiceStatus.container_name}
                    </span>
                  )}
                  <span className="badge-muted badge">Port {trinoServiceStatus.port}</span>
                  {!trinoServiceStatus.docker_available && (
                    <span className="badge-muted badge">Docker unavailable</span>
                  )}
                </div>
              )}

              {trinoServiceStatus && (
                <p className="text-sm">
                  URL:{" "}
                  <code className="rounded px-1.5 py-0.5 text-xs" style={{ background: "var(--color-surface-subtle)" }}>
                    {trinoServiceStatus.url}
                  </code>
                </p>
              )}

              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                Runs <code className="text-xs">docker compose up -d trino</code> from the project root. Use host{" "}
                <code className="text-xs">localhost</code> and port <code className="text-xs">8081</code> in Trino
                settings when the API runs on your machine.
              </p>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={trinoServiceBusy || trinoServiceIsRunning || !trinoServiceStatus?.docker_available}
                  onClick={() => trinoServiceStart.mutate()}
                >
                  {trinoServiceStart.isPending ? "Starting…" : "Start"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={trinoServiceBusy || !trinoServiceIsRunning}
                  onClick={() => trinoServiceStop.mutate()}
                >
                  {trinoServiceStop.isPending ? "Stopping…" : "Stop"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={trinoServiceBusy || !trinoServiceIsRunning}
                  onClick={() => trinoServiceRestart.mutate()}
                >
                  {trinoServiceRestart.isPending ? "Restarting…" : "Restart"}
                </button>
              </div>

              {trinoServiceStatus?.source === "external" && (
                <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                  External container — Stop runs <code className="text-xs">docker compose stop trino</code>.
                </p>
              )}

              {trinoServiceNotice && (
                <p className={trinoServiceNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>
                  {trinoServiceNotice.text}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save catalog & service settings"}
            </button>
            <p className="text-xs text-zinc-500">
              Writes to {data.env_path}. Restart API, MCP, or Trino after connection changes.
            </p>
          </div>

          {message && <p className="alert-ok">{message}</p>}
          {error && <p className="alert-error">{error}</p>}
        </>
      )}
    </div>
  );
}
