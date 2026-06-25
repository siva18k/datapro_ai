import { Link } from "react-router-dom";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";

export function ApiOfflineBanner() {
  const {
    apiOnline,
    bootstrapPhase,
    bootstrapMessage,
    starting,
    showStartButton,
    canStartFromWeb,
    retryConnection,
  } = useApiConnection();
  const startApi = useStartApiFromWeb();

  if (apiOnline) return null;

  const busy = starting || startApi.isPending || bootstrapPhase === "checking";

  if (busy) {
    return (
      <div className="message-bar message-bar--info" role="status" aria-live="polite">
        <div className="message-bar-inner">
          <div>
            <p className="message-bar-title">
              {bootstrapMessage ?? "Starting API server…"}
            </p>
            <p className="message-bar-hint">
              {bootstrapPhase === "checking"
                ? "Checking whether the API is already running…"
                : "Waiting for the API on port 8080. This usually takes a few seconds."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const errorMessage =
    startApi.data && !startApi.data.ok ? startApi.data.message : bootstrapMessage;

  return (
    <div className="message-bar message-bar--warning" role="status" aria-live="polite">
      <div className="message-bar-inner">
        <div>
          <p className="message-bar-title">API server offline</p>
          {errorMessage ? (
            <p className="message-bar-hint">{errorMessage}</p>
          ) : (
            <p className="message-bar-hint">
              {canStartFromWeb
                ? "Start the API server to use Catalog, Ask, and Analytics."
                : "Run uvicorn on port 8080 or see Settings."}
            </p>
          )}
          {startApi.error && (
            <p className="message-bar-hint">
              {startApi.error instanceof Error
                ? startApi.error.message
                : "Could not start the API server."}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {showStartButton && (
            <button
              type="button"
              className="btn btn-sm shrink-0"
              disabled={startApi.isPending}
              onClick={() => startApi.mutate()}
            >
              {startApi.isPending ? "Starting…" : "Start API server"}
            </button>
          )}
          {!canStartFromWeb && (
            <Link to="/settings" className="btn btn-secondary btn-sm shrink-0">
              Settings
            </Link>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm shrink-0"
            disabled={startApi.isPending}
            onClick={() => void retryConnection()}
          >
            Retry
          </button>
        </div>
      </div>
    </div>
  );
}
