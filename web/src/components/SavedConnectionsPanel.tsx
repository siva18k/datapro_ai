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

  const existingNames = (connections ?? [])
    .filter((conn) => conn.id !== editing?.id)
    .map((conn) => conn.name);

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Dataset connections</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
            Named Postgres connections for Database datasets in the catalog
          </p>
        </div>
        <button type="button" className="btn btn-sm shrink-0" onClick={openNew}>
          + Add connection
        </button>
      </div>

      {isLoading && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Loading connections…
        </p>
      )}

      {!isLoading && !connections?.length && (
        <div className="settings-connections-empty">
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            No saved connections yet. Add a uniquely named connection to link from catalog datasets.
          </p>
        </div>
      )}

      {!!connections?.length && (
        <ul className="saved-connections-grid">
          {connections.map((conn) => (
            <li key={conn.id} className="saved-connection-card">
              <div className="saved-connection-card-header">
                <p className="saved-connection-card-name">{conn.name}</p>
                <span className="saved-connection-card-badge">Dataset</span>
              </div>
              <p className="saved-connection-card-meta">
                {conn.user}@{conn.host}:{conn.port}
              </p>
              <p className="saved-connection-card-meta">
                {conn.database}.{conn.schema} · SSL {conn.sslmode}
              </p>
              <div className="saved-connection-card-actions">
                <button type="button" className="btn-ghost btn-sm" onClick={() => openEdit(conn)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-ghost btn-sm saved-connection-delete"
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
        existingNames={existingNames}
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
