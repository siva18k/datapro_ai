import { isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";

export function ApiOfflinePanel({ title = "API server offline" }: { title?: string }) {
  const { refresh, checking, connecting } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();
  const startApi = useStartApiFromWeb();

  const busy = checking || connecting || startApi.isPending;
  const statusMessage = startApi.isPending
    ? "Starting API server…"
    : connecting
      ? "Waiting for API connection…"
      : checking
        ? "Checking connection…"
        : null;

  return (
    <div className="card card-pad max-w-xl space-y-3">
      <h2 className="font-semibold">{title}</h2>

      {statusMessage ? (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          {statusMessage} This may take a few seconds while the server loads.
        </p>
      ) : (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          API server offline on port 8080.{" "}
          {canStartFromWeb ? "Start it here or from Settings." : "Run uvicorn, then refresh."}
        </p>
      )}

      {canStartFromWeb ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => startApi.mutate()}>
            {startApi.isPending || connecting ? "Starting…" : "Start API server"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void refresh()}>
            {checking ? "Checking…" : "Retry connection"}
          </button>
        </div>
      ) : (
        <>
          <pre
            className="overflow-x-auto rounded-lg p-3 text-xs"
            style={{ background: "var(--color-code-bg)", color: "var(--color-text)" }}
          >
            cd data-pro{"\n"}
            uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
          </pre>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void refresh()}>
            {checking ? "Checking…" : "Retry connection"}
          </button>
        </>
      )}

      {startApi.data && !busy && (
        <p className={startApi.data.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{startApi.data.message}</p>
      )}
      {startApi.error && !busy && <p className="alert-error text-sm">{String(startApi.error)}</p>}
    </div>
  );
}
