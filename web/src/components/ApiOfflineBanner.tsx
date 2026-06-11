import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { devBootstrap, isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";

export function ApiOfflineBanner() {
  const { apiOnline, checking, refresh } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();

  const startApi = useMutation({
    mutationFn: devBootstrap.startApi,
    onSuccess: (res) => {
      if (res.reachable) void refresh();
    },
  });

  if (apiOnline || checking) return null;

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <p>
          API server offline.{" "}
          {canStartFromWeb ? (
            <>
              <strong>Start API server</strong> or{" "}
              <Link to="/settings" className="font-medium underline underline-offset-2">
                Settings
              </Link>
              .
            </>
          ) : (
            <>
              See{" "}
              <Link to="/settings" className="font-medium underline underline-offset-2">
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
