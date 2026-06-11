import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type SavedDbConnection } from "../api/client";
import { DbConnectionModal } from "./DbConnectionModal";

export function SavedConnectionsPanel() {
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SavedDbConnection | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: connections, isLoading } = useQuery({
    queryKey: ["db-connections"],
    queryFn: api.listDbConnections,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteDbConnection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["db-connections"] });
      setMessage("Connection removed.");
      setError(null);
    },
    onError: (err) => {
      setError(String(err));
      setMessage(null);
    },
  });

  const openNew = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = (conn: SavedDbConnection) => {
    setEditing(conn);
    setModalOpen(true);
  };

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Dataset connections</h2>
          <p className="mt-1 text-sm text-zinc-500">For Database datasets in catalog</p>
        </div>
        <button type="button" className="btn btn-sm shrink-0" onClick={openNew}>
          + Add
        </button>
      </div>

      {isLoading && <p className="text-sm text-zinc-500">Loading connections…</p>}

      {!isLoading && !connections?.length && (
        <p className="rounded-lg border border-dashed border-zinc-200 px-4 py-6 text-center text-sm text-zinc-500">
          No saved connections yet.
        </p>
      )}

      {!!connections?.length && (
        <ul className="saved-connections-list space-y-2">
          {connections.map((conn) => (
            <li key={conn.id} className="saved-connection-item">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-zinc-900">{conn.name}</p>
                <p className="truncate text-xs text-zinc-500">
                  {conn.user}@{conn.host}:{conn.port} · {conn.database}.{conn.schema}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button type="button" className="btn-ghost btn-sm" onClick={() => openEdit(conn)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-ghost btn-sm text-red-600 hover:bg-red-50"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete connection "${conn.name}"?`)) remove.mutate(conn.id);
                  }}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {message && <p className="alert-ok">{message}</p>}
      {error && <p className="alert-error">{error}</p>}

      <DbConnectionModal
        open={modalOpen}
        connection={editing}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: ["db-connections"] });
          setMessage(editing ? "Connection updated." : "Connection saved.");
          setError(null);
          setEditing(null);
        }}
      />
    </div>
  );
}
