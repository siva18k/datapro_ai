import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CONNECTOR_LABELS } from "../types";
import { DbConnectionModal } from "./DbConnectionModal";

const CONNECTORS = ["postgres", "upload", "file_path", "api", "sharepoint", "web_url"] as const;
const NEW_CONNECTION = "__new__";
const REMOTE_CONNECTORS = new Set(["api", "web_url", "sharepoint"]);

type Props = {
  domainId: string;
  onCreated: (datasetId: string) => void;
  onCancel: () => void;
};

function buildConfig(
  connector: string,
  fields: {
    folderPath: string;
    url: string;
    baseUrl: string;
    endpoints: string;
    authToken: string;
  },
): Record<string, unknown> {
  switch (connector) {
    case "file_path":
      return { path: fields.folderPath.trim() || "sample_docs" };
    case "web_url":
    case "sharepoint": {
      const cfg: Record<string, unknown> = { url: fields.url.trim() };
      if (fields.authToken.trim()) cfg.auth_token = fields.authToken.trim();
      return cfg;
    }
    case "api": {
      const paths = fields.endpoints
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const cfg: Record<string, unknown> = {
        base_url: fields.baseUrl.trim(),
        endpoints: paths.length ? paths : [""],
      };
      if (fields.authToken.trim()) cfg.auth_token = fields.authToken.trim();
      return cfg;
    }
    default:
      return {};
  }
}

function connectorReady(connector: string, name: string, connectionId: string, url: string, baseUrl: string): boolean {
  if (!name.trim()) return false;
  if (connector === "postgres") return !!connectionId;
  if (connector === "web_url" || connector === "sharepoint") return !!url.trim();
  if (connector === "api") return !!baseUrl.trim();
  return true;
}

export function AddDatasetForm({ domainId, onCreated, onCancel }: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [connector, setConnector] = useState<string>("upload");
  const [connectionId, setConnectionId] = useState("");
  const [showConnectionModal, setShowConnectionModal] = useState(false);
  const [folderPath, setFolderPath] = useState("sample_docs");
  const [url, setUrl] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [endpoints, setEndpoints] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: dbConnections } = useQuery({
    queryKey: ["db-connections"],
    queryFn: api.listDbConnections,
    enabled: connector === "postgres",
  });

  const { data: fileTypes } = useQuery({
    queryKey: ["supported-file-types"],
    queryFn: () => api.supportedFileTypes(),
    enabled: connector === "upload",
  });

  useEffect(() => {
    setError(null);
  }, [connector]);

  const create = useMutation({
    mutationFn: async () => {
      setError(null);
      let config: Record<string, unknown> = buildConfig(connector, {
        folderPath,
        url,
        baseUrl,
        endpoints,
        authToken,
      });
      if (connector === "postgres") {
        config = await api.getDbConnectionConfig(connectionId);
      }
      const dataset = await api.createDataset(domainId, {
        name: name.trim(),
        connector,
        config,
      });
      const warnings: string[] = [];
      if (connector === "upload" && pendingFiles.length) {
        try {
          await api.uploadFiles(dataset.id, pendingFiles);
        } catch (err) {
          warnings.push(err instanceof Error ? err.message : String(err));
        }
      }
      if (REMOTE_CONNECTORS.has(connector)) {
        try {
          await api.syncDataset(dataset.id);
        } catch (err) {
          warnings.push(err instanceof Error ? err.message : String(err));
        }
      }
      return { dataset, warnings };
    },
    onSuccess: ({ dataset, warnings }) => {
      qc.invalidateQueries({ queryKey: ["datasets", domainId] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["assets", dataset.id] });
      if (warnings.length) {
        setError(`Dataset created, but: ${warnings.join("; ")}`);
        onCreated(dataset.id);
        return;
      }
      onCreated(dataset.id);
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });

  const accept = fileTypes?.accept ?? ".pdf,.md,.txt,.json";
  const typeHint = fileTypes?.extensions.join(", ") ?? ".pdf, .md, .txt, .json";
  const ready = connectorReady(connector, name, connectionId, url, baseUrl);

  return (
    <div className="catalog-add-dataset-form">
      <div className="add-dataset-grid">
        <div className="field mb-0">
          <label className="label">Dataset name</label>
          <input
            className="input"
            placeholder="e.g. Products"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="field mb-0">
          <label className="label">Format</label>
          <select
            className="select"
            value={connector}
            onChange={(e) => {
              setConnector(e.target.value);
              setConnectionId("");
              setError(null);
            }}
          >
            {CONNECTORS.map((c) => (
              <option key={c} value={c}>
                {CONNECTOR_LABELS[c]}
              </option>
            ))}
          </select>
        </div>

        {connector === "postgres" && (
          <div className="field mb-0 add-dataset-field-wide">
            <label className="label">Connection</label>
            <select
              className="select"
              value={connectionId || (dbConnections?.length ? "" : NEW_CONNECTION)}
              onChange={(e) => {
                const value = e.target.value;
                if (value === NEW_CONNECTION) {
                  setConnectionId("");
                  setShowConnectionModal(true);
                } else {
                  setConnectionId(value);
                }
              }}
            >
              {!!dbConnections?.length && (
                <option value="" disabled>
                  Select connection…
                </option>
              )}
              <option value={NEW_CONNECTION}>
                {dbConnections?.length ? "+ New connection…" : "+ Set up connection…"}
              </option>
              {dbConnections?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.host})
                </option>
              ))}
            </select>
          </div>
        )}

        {connector === "file_path" && (
          <div className="field mb-0 add-dataset-field-wide">
            <label className="label">Folder path</label>
            <input
              className="input"
              placeholder="sample_docs or data/domain/dataset"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
            />
          </div>
        )}

        {(connector === "web_url" || connector === "sharepoint") && (
          <>
            <div className="field mb-0 add-dataset-field-wide">
              <label className="label">{connector === "sharepoint" ? "SharePoint / document URL" : "Web URL"}</label>
              <input
                className="input"
                type="url"
                placeholder="https://…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            {connector === "sharepoint" && (
              <div className="field mb-0 add-dataset-field-wide">
                <label className="label">Auth token (optional Bearer)</label>
                <input
                  className="input"
                  type="password"
                  value={authToken}
                  onChange={(e) => setAuthToken(e.target.value)}
                />
              </div>
            )}
          </>
        )}

        {connector === "api" && (
          <>
            <div className="field mb-0 add-dataset-field-wide">
              <label className="label">Base URL</label>
              <input
                className="input"
                type="url"
                placeholder="https://api.example.com"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </div>
            <div className="field mb-0 add-dataset-field-wide">
              <label className="label">Endpoints (comma-separated paths)</label>
              <input
                className="input"
                placeholder="/v1/products, /v1/pricing"
                value={endpoints}
                onChange={(e) => setEndpoints(e.target.value)}
              />
            </div>
            <div className="field mb-0 add-dataset-field-wide">
              <label className="label">Auth token (optional Bearer)</label>
              <input
                className="input"
                type="password"
                value={authToken}
                onChange={(e) => setAuthToken(e.target.value)}
              />
            </div>
          </>
        )}
      </div>

      {connector === "upload" && (
        <div className="add-dataset-upload catalog-themed-box mt-3">
          <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
            Upload files (optional now)
          </p>
          <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
            Supported: {typeHint}. You can also upload after creating the dataset.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="btn btn-secondary btn-sm file-upload-btn">
              Choose files
              <input
                type="file"
                className="file-upload-input"
                accept={accept}
                multiple
                onChange={(e) => setPendingFiles(Array.from(e.target.files ?? []))}
              />
            </label>
            {pendingFiles.length > 0 && (
              <span className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                {pendingFiles.length} file(s): {pendingFiles.map((f) => f.name).join(", ")}
              </span>
            )}
          </div>
        </div>
      )}

      <p className="add-dataset-hint mt-3 text-sm" style={{ color: "var(--color-text-muted)" }}>
        {connector === "postgres" && "After create: discover tables on the Data tab, then RAG for catalog metadata."}
        {connector === "upload" && "Files are stored under data/{domain}/{dataset}/. Use RAG tab to embed."}
        {connector === "file_path" && "Reads documents from the folder path on disk."}
        {connector === "api" && "Creates the dataset and syncs API responses into the cache on create."}
        {connector === "web_url" && "Creates the dataset and fetches the URL into the cache on create."}
        {connector === "sharepoint" && "Creates the dataset and syncs the document link on create (Bearer token if needed)."}
      </p>

      {error && (
        <p className={error.startsWith("Dataset created") ? "alert-ok mt-3" : "alert-error mt-3"}>{error}</p>
      )}

      <div className="add-dataset-form-actions">
        <button
          type="button"
          className="btn"
          disabled={!ready || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Creating…" : connector === "upload" && pendingFiles.length ? "Create & upload" : "Create"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={create.isPending}>
          Cancel
        </button>
      </div>

      <DbConnectionModal
        open={showConnectionModal}
        onClose={() => setShowConnectionModal(false)}
        onSaved={(conn) => {
          qc.invalidateQueries({ queryKey: ["db-connections"] });
          setConnectionId(conn.id);
        }}
      />
    </div>
  );
}
