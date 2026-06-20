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

function isFormValid(form: DbConnectionPayload): boolean {
  return Boolean(form.name.trim() && form.host.trim() && form.user.trim() && form.database.trim());
}

function hasFormChanges(form: DbConnectionPayload, initial: DbConnectionPayload, isEdit: boolean): boolean {
  if (!isEdit) return true;
  const keys: (keyof DbConnectionPayload)[] = ["name", "host", "port", "user", "database", "schema", "sslmode"];
  if (keys.some((key) => form[key] !== initial[key])) return true;
  return form.password.trim().length > 0;
}

export function DbConnectionModal({
  open,
  connection,
  existingNames = [],
  onClose,
  onSaved,
}: {
  open: boolean;
  connection?: SavedDbConnection | null;
  existingNames?: string[];
  onClose: () => void;
  onSaved: (connection: SavedDbConnection) => void;
}) {
  const isEdit = !!connection;
  const [form, setForm] = useState<DbConnectionPayload>(emptyForm());
  const [initialForm, setInitialForm] = useState<DbConnectionPayload>(emptyForm());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const next = connection
      ? {
          name: connection.name,
          host: connection.host,
          port: connection.port,
          user: connection.user,
          password: "",
          database: connection.database,
          schema: connection.schema,
          sslmode: connection.sslmode,
        }
      : emptyForm();
    setForm(next);
    setInitialForm(next);
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

  const trimmedName = form.name.trim();
  const nameTaken = trimmedName
    ? existingNames.some((name) => name.trim().toLowerCase() === trimmedName.toLowerCase())
    : false;
  const formChanged = hasFormChanges(form, initialForm, isEdit);
  const formValid = isFormValid(form);
  const canSave = formChanged && formValid && !nameTaken && !save.isPending;

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
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Reusable Postgres connection for catalog datasets. Each connection needs a unique name.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="field mb-0 sm:col-span-2">
            <label className="label">Connection name</label>
            <input
              className="input"
              placeholder="e.g. Finance_DB"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            {nameTaken && (
              <p className="alert-error mt-2 text-xs">This name is already used. Choose a unique name.</p>
            )}
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
        <div className="modal-actions modal-actions--split">
          <button type="button" className="btn" disabled={!canSave} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          <div className="modal-actions-end">
            <button type="button" className="btn btn-secondary" disabled={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Testing…" : "Test"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
