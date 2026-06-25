import { isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";
import { ApiConnectingPanel } from "./ApiConnectingPanel";

export function ApiOfflinePanel({ title = "API server offline" }: { title?: string }) {
  const {
    bootstrapPhase,
    bootstrapMessage,
    starting,
    showStartButton,
    retryConnection,
  } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();
  const startApi = useStartApiFromWeb();

  const busy = starting || startApi.isPending || bootstrapPhase === "checking";

  if (busy) {
    return (
      <ApiConnectingPanel title={bootstrapMessage ?? "Starting API server…"} />
    );
  }

  const errorMessage =
    startApi.data && !startApi.data.ok ? startApi.data.message : bootstrapMessage;

  return (
    <div className="card card-pad max-w-xl space-y-3">
      <h2 className="font-semibold">{title}</h2>

      <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
        API server offline on port 8080.{" "}
        {canStartFromWeb
          ? "Use Start API server below (also shown in the banner)."
          : "Run uvicorn, then retry."}
      </p>

      {errorMessage && <p className="alert-error text-sm">{errorMessage}</p>}
      {startApi.error && <p className="alert-error text-sm">{String(startApi.error)}</p>}

      <div className="flex flex-wrap gap-2">
        {showStartButton && (
          <button
            type="button"
            className="btn btn-sm"
            disabled={startApi.isPending}
            onClick={() => startApi.mutate()}
          >
            {startApi.isPending ? "Starting…" : "Start API server"}
          </button>
        )}
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void retryConnection()}>
          Retry connection
        </button>
      </div>

      {!canStartFromWeb && (
        <pre
          className="overflow-x-auto rounded-lg p-3 text-xs"
          style={{ background: "var(--color-code-bg)", color: "var(--color-text)" }}
        >
          cd datapro{"\n"}
          uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
        </pre>
      )}
    </div>
  );
}
