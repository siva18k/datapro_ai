import { Link } from "react-router-dom";
import { isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";

export function ApiOfflineBanner() {
  const { apiOnline, apiPending, starting, connecting, retryConnection } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();
  const startApi = useStartApiFromWeb();
  const busy = apiPending || startApi.isPending;

  if (apiOnline) return null;

  if (busy) {
    const title = starting || startApi.isPending
      ? "Starting API server…"
      : connecting
        ? "Checking API connection…"
        : "Checking API connection…";
    return (
      <div className="message-bar message-bar--info" role="status" aria-live="polite">
        <div className="message-bar-inner">
          <div>
            <p className="message-bar-title">{title}</p>
            <p className="message-bar-hint">
              Checking every few seconds. This may take up to 10 seconds while the server loads.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="message-bar message-bar--warning" role="status" aria-live="polite">
      <div className="message-bar-inner">
        <p>
          API server offline.{" "}
          {canStartFromWeb ? (
            <>
              <strong>Start API server</strong> or{" "}
              <Link to="/settings" className="message-bar-link">
                Settings
              </Link>
              .
            </>
          ) : (
            <>
              See{" "}
              <Link to="/settings" className="message-bar-link">
                Settings
              </Link>{" "}
              or run uvicorn on 8080.
            </>
          )}
        </p>
        <div className="flex flex-wrap gap-2">
          {canStartFromWeb && (
            <button type="button" className="btn btn-sm" onClick={() => startApi.mutate()}>
              Start API server
            </button>
          )}
          <button type="button" className="btn btn-secondary btn-sm shrink-0" onClick={() => void retryConnection()}>
            Retry connection
          </button>
        </div>
      </div>
    </div>
  );
}
