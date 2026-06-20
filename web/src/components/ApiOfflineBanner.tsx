import { Link } from "react-router-dom";
import { isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";
import { useStartApiFromWeb } from "../hooks/useStartApiFromWeb";

export function ApiOfflineBanner() {
  const { apiOnline, checking, connecting, refresh } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();
  const startApi = useStartApiFromWeb();

  if (apiOnline) return null;

  if (checking || connecting || startApi.isPending) {
    return (
      <div className="message-bar message-bar--info" role="status" aria-live="polite">
        <div className="message-bar-inner">
          <div>
            <p className="message-bar-title">
              {startApi.isPending ? "Starting API server…" : "Waiting for API connection…"}
            </p>
            <p className="message-bar-hint">This may take a few seconds while the server loads.</p>
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
            <button
              type="button"
              className="btn btn-sm"
              disabled={startApi.isPending}
              onClick={() => startApi.mutate()}
            >
              {startApi.isPending ? "Starting…" : "Start API server"}
            </button>
          )}
          <button type="button" className="btn btn-secondary btn-sm shrink-0" onClick={() => void refresh()}>
            Retry connection
          </button>
        </div>
      </div>
    </div>
  );
}
