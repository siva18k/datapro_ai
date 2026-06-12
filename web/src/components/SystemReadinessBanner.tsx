import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApiConnection } from "../context/ApiConnectionContext";

export function SystemReadinessBanner() {
  const { apiOnline } = useApiConnection();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["readiness"],
    queryFn: api.readiness,
    enabled: apiOnline,
    refetchInterval: apiOnline ? 30_000 : false,
    retry: 1,
  });

  if (!apiOnline || isLoading || !data || data.ok) return null;

  return (
    <div className="message-bar message-bar--warning" role="status" aria-live="polite">
      <div className="message-bar-inner">
        <div className="message-bar-content">
          <p className="message-bar-title">Some data services are unavailable</p>
          <ul className="message-bar-list">
            {data.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
          <p className="message-bar-hint">
            Check{" "}
            <Link to="/settings" className="message-bar-link">
              Settings → Database
            </Link>{" "}
            or run migrations if tables are missing.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm shrink-0"
          disabled={isFetching}
          onClick={() => void refetch()}
        >
          {isFetching ? "Checking…" : "Recheck"}
        </button>
      </div>
    </div>
  );
}
