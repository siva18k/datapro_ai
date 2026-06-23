import { isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";
import { ApiConnectingPanel } from "./ApiConnectingPanel";

export function ApiOfflinePanel({ title = "API server offline" }: { title?: string }) {
  const { retryConnection, apiPending, starting } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();
  const startApi = useStartApiFromWeb();

  const busy = apiPending || startApi.isPending;

  if (busy) {
    return (
      <ApiConnectingPanel
        title={
          starting || startApi.isPending
            ? "Starting API server…"
            : "Checking API connection…"
        }
      />
    );
  }

  return (
    <div className="card card-pad max-w-xl space-y-3">
      <h2 className="font-semibold">{title}</h2>

      <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
        API server offline on port 8080.{" "}
        {canStartFromWeb ? "Start it here or from Settings." : "Run uvicorn, then retry."}
      </p>

      {canStartFromWeb ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm" onClick={() => startApi.mutate()}>
            Start API server
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void retryConnection()}>
            Retry connection
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
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void retryConnection()}>
            Retry connection
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
