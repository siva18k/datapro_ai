import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type SavedDbConnection, type TrinoSettingsPayload } from "../api/client";
import { DbConnectionModal } from "./DbConnectionModal";
import { DbConnectionSummary } from "./DbConnectionSummary";
import { TrinoServerCard } from "./TrinoServerCard";

export function SavedConnectionsPanel({
  catalog,
  trino,
  trinoPassword,
  trinoEditing,
  trinoNotice,
  onTrinoEdit,
  onTrinoCancel,
  onTrinoChange,
  onTrinoPasswordChange,
  onTrinoNotice,
}: {
  catalog?: ReactNode;
  trino?: TrinoSettingsPayload;
  trinoPassword?: string;
  trinoEditing?: boolean;
  trinoNotice?: { ok: boolean; text: string } | null;
  onTrinoEdit?: () => void;
  onTrinoCancel?: () => void;
  onTrinoChange?: (patch: Partial<TrinoSettingsPayload>) => void;
  onTrinoPasswordChange?: (value: string) => void;
  onTrinoNotice?: (notice: { ok: boolean; text: string } | null) => void;
}) {
  const qc = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SavedDbConnection | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

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

  const testConn = useMutation({
    mutationFn: (id: string) => api.testDbConnectionById(id),
    onSuccess: (res) => {
      setMessage(res.message);
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

  const datasetCount = connections?.length ?? 0;
  const trinoConfigured = Boolean(trino?.host?.trim());
  const showTrinoCard = Boolean(
    trino && onTrinoEdit && onTrinoCancel && onTrinoChange && onTrinoPasswordChange && onTrinoNotice,
  );

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Connections</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
            Catalog database, Trino coordinator, native Postgres, and warehouse bindings for business datasets
          </p>
        </div>
        <button type="button" className="btn btn-sm shrink-0" onClick={openNew}>
          + Add connection
        </button>
      </div>

      {isLoading && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Loading dataset connections…
        </p>
      )}

      <ul className="saved-connections-grid">
        {catalog}
        {showTrinoCard && trino ? (
          <TrinoServerCard
            form={trino}
            password={trinoPassword ?? ""}
            passwordSet={settings?.trino?.password_set ?? false}
            configured={trinoConfigured}
            editing={Boolean(trinoEditing)}
            notice={trinoNotice ?? null}
            onEdit={onTrinoEdit!}
            onCancel={onTrinoCancel!}
            onChange={onTrinoChange!}
            onPasswordChange={onTrinoPasswordChange!}
            onNotice={onTrinoNotice!}
          />
        ) : null}
        {!isLoading &&
          connections?.map((conn) => (
            <li key={conn.id} className="saved-connection-card">
              <div className="saved-connection-card-header">
                <p className="saved-connection-card-name">{conn.name}</p>
                <span className="saved-connection-card-badge">
                  {conn.connector === "postgres" ? "Native PostgreSQL" : "Trino catalog"}
                </span>
              </div>
              <DbConnectionSummary
                connector={conn.connector}
                warehouseTypeLabel={conn.warehouse_type_label}
                catalog={conn.catalog}
                schema={conn.schema}
                user={conn.user}
                host={conn.host}
                database={conn.database}
                snowflakeAccount={conn.snowflake_account}
              />
              <div className="saved-connection-card-actions">
                <button type="button" className="btn-ghost btn-sm" onClick={() => openEdit(conn)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  disabled={testConn.isPending}
                  onClick={() => testConn.mutate(conn.id)}
                >
                  {testConn.isPending ? "Testing…" : "Test"}
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

      {!isLoading && datasetCount === 0 && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          No business connections yet. Add a native Postgres or Trino warehouse connection, then create structured datasets from it.
        </p>
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
