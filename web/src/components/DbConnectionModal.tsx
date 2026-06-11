import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type DbConnectionPayload, type SavedDbConnection } from "../api/client";

const emptyForm = (): DbConnectionPayload => ({
  name: "",
  host: "",
  port: 5432,
  user: "",
  password: "",
  database: "postgres",
  schema: "public",
  sslmode: "require",
});

export function DbConnectionModal({
  open,
  connection,
  onClose,
  onSaved,
}: {
  open: boolean;
  connection?: SavedDbConnection | null;
  onClose: () => void;
  onSaved: (connection: SavedDbConnection) => void;
}) {
  const isEdit = !!connection;
  const [form, setForm] = useState<DbConnectionPayload>(emptyForm());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (connection) {
      setForm({
        name: connection.name,
        host: connection.host,
        port: connection.port,
        user: connection.user,
        password: "",
        database: connection.database,
        schema: connection.schema,
        sslmode: connection.sslmode,
      });
    } else {
      setForm(emptyForm());
    }
    setMessage(null);
    setError(null);
  }, [open, connection]);

  const test = useMutation({
    mutationFn: () => api.testDbConnection(form),
    onSuccess: (res) => {
      setMessage(res.message);
      setError(null);
    },
    onError: (err) => {
      setError(String(err));
      setMessage(null);
    },
  });

  const save = useMutation({
    mutationFn: () => {
      if (isEdit && connection) {
        return api.updateDbConnection(connection.id, {
          ...form,
          password: form.password || undefined,
        });
      }
      return api.createDbConnection(form);
    },
    onSuccess: (conn) => {
      onSaved(conn);
      onClose();
    },
    onError: (err) => setError(String(err)),
  });

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="db-conn-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card">
        <div className="modal-header">
          <h2 id="db-conn-title" className="text-lg font-semibold">
            {isEdit ? "Edit database connection" : "New database connection"}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <p className="text-sm text-zinc-500">Reusable Postgres connection for datasets.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="field mb-0 sm:col-span-2">
            <label className="label">Connection name</label>
            <input
              className="input"
              placeholder="e.g. Finance warehouse"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          {(
            [
              ["host", "Host", "text"],
              ["port", "Port", "number"],
              ["user", "User", "text"],
              ["password", "Password", "password"],
              ["database", "Database", "text"],
              ["schema", "Schema", "text"],
            ] as const
          ).map(([key, label, type]) => (
            <div key={key} className="field mb-0">
              <label className="label">{label}</label>
              <input
                className="input"
                type={type}
                placeholder={
                  key === "password" && connection?.password_set ? "Leave blank to keep current password" : undefined
                }
                value={String(form[key])}
                onChange={(e) =>
                  setForm({
                    ...form,
                    [key]: key === "port" ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            </div>
          ))}
          <div className="field mb-0">
            <label className="label">SSL mode</label>
            <select
              className="select"
              value={form.sslmode}
              onChange={(e) => setForm({ ...form, sslmode: e.target.value })}
            >
              <option value="require">require</option>
              <option value="verify-full">verify-full</option>
              <option value="prefer">prefer</option>
              <option value="disable">disable</option>
            </select>
          </div>
        </div>
        {message && <p className="alert-ok mt-3">{message}</p>}
        {error && <p className="alert-error mt-3">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" disabled={test.isPending} onClick={() => test.mutate()}>
            {test.isPending ? "Testing…" : "Test"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={save.isPending || !form.name.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : isEdit ? "Update connection" : "Save connection"}
          </button>
        </div>
      </div>
    </div>
  );
}
