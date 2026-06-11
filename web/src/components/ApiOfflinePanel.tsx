import { useMutation } from "@tanstack/react-query";
import { devBootstrap, isDevBootstrapAvailable } from "../api/devBootstrap";
import { useApiConnection } from "../context/ApiConnectionContext";

export function ApiOfflinePanel({ title = "API server offline" }: { title?: string }) {
  const { refresh, checking } = useApiConnection();
  const canStartFromWeb = isDevBootstrapAvailable();

  const startApi = useMutation({
    mutationFn: devBootstrap.startApi,
    onSuccess: (res) => {
      if (res.reachable) void refresh();
    },
  });

  const busy = checking || startApi.isPending;

  return (
    <div className="card card-pad max-w-xl space-y-3">
      <h2 className="font-semibold">{title}</h2>
      <p className="text-sm text-zinc-600">
        API server offline on port 8080.{" "}
        {canStartFromWeb ? "Start it here or from Settings." : "Run uvicorn, then refresh."}
      </p>

      {canStartFromWeb ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy}
            onClick={() => startApi.mutate()}
          >
            {startApi.isPending ? "Starting…" : "Start API server"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void refresh()}>
            {checking ? "Checking…" : "Retry connection"}
          </button>
        </div>
      ) : (
        <>
          <pre className="overflow-x-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
            cd data-pro{"\n"}
            uvicorn api.main:app --reload --host 127.0.0.1 --port 8080
          </pre>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void refresh()}>
            {checking ? "Checking…" : "Retry connection"}
          </button>
        </>
      )}

      {startApi.data && (
        <p className={startApi.data.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{startApi.data.message}</p>
      )}
      {startApi.error && <p className="alert-error text-sm">{String(startApi.error)}</p>}
    </div>
  );
}
