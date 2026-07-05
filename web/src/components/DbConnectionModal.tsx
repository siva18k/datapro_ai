import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type DbConnectionPayload,
  type SavedDbConnection,
  type WarehouseConnectorField,
} from "../api/client";
import { suggestCatalogName, TRINO_CONNECTOR } from "../utils/databaseConnectors";
import {
  DEFAULT_WAREHOUSE_TYPE,
  defaultsForWarehouseType,
  fieldValue,
  groupLabel,
  isWarehouseFormValid,
  warehouseConnectorById,
  warehouseGroups,
} from "../utils/trinoWarehouseConnectors";

function emptyForm(): DbConnectionPayload {
  return {
    name: "",
    connector: TRINO_CONNECTOR,
    warehouse_type: DEFAULT_WAREHOUSE_TYPE,
    catalog: "",
    schema: "public",
    host: "",
    port: 5432,
    user: "",
    password: "",
    database: "postgres",
    sslmode: "require",
    extra: {},
  };
}

function connectionToForm(connection: SavedDbConnection): DbConnectionPayload {
  const extra = { ...(connection.extra ?? {}) };
  return {
    name: connection.name,
    connector: TRINO_CONNECTOR,
    warehouse_type: connection.warehouse_type || DEFAULT_WAREHOUSE_TYPE,
    catalog: connection.catalog,
    schema: connection.schema,
    host: connection.host,
    port: connection.port,
    user: connection.user,
    database: connection.database,
    sslmode: connection.sslmode ?? extra.sslmode ?? "require",
    encrypt: connection.encrypt ?? extra.encrypt,
    oracle_connect_mode: connection.oracle_connect_mode ?? extra.oracle_connect_mode,
    oracle_service: connection.oracle_service ?? extra.oracle_service,
    snowflake_account: connection.snowflake_account ?? extra.snowflake_account,
    snowflake_warehouse: connection.snowflake_warehouse ?? extra.snowflake_warehouse,
    snowflake_role: connection.snowflake_role ?? extra.snowflake_role,
    trino_connector_name: connection.trino_connector_name ?? extra.trino_connector_name,
    connection_url: connection.connection_url ?? extra.connection_url,
    extra,
  };
}

function hasFormChanges(
  form: DbConnectionPayload,
  initial: DbConnectionPayload,
  isEdit: boolean,
  password: string,
): boolean {
  if (!isEdit) return true;
  if (password.length > 0) return true;
  return JSON.stringify(form) !== JSON.stringify(initial);
}

function ConnectorField({
  field,
  form,
  password,
  passwordSet,
  onPasswordChange,
  onChange,
}: {
  field: WarehouseConnectorField;
  form: DbConnectionPayload;
  password: string;
  passwordSet?: boolean;
  onPasswordChange: (value: string) => void;
  onChange: (patch: Partial<DbConnectionPayload>) => void;
}) {
  if (field.id === "password") {
    return (
      <div className="field mb-0">
        <label className="label">{field.label}</label>
        <input
          className="input"
          type="password"
          placeholder={passwordSet ? "Leave blank to keep current password" : field.placeholder}
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
        />
      </div>
    );
  }

  const value = field.id === "port" ? String(form.port ?? "") : fieldValue(form, field.id);

  if (field.type === "select") {
    return (
      <div className="field mb-0">
        <label className="label">{field.label}</label>
        <select
          className="select"
          value={value}
          onChange={(e) => onChange({ [field.id]: e.target.value } as Partial<DbConnectionPayload>)}
        >
          {(field.options ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={`field mb-0${field.id === "connection_url" ? " sm:col-span-2" : ""}`}>
      <label className="label">{field.label}</label>
      <input
        className={`input${field.id !== "port" ? " font-mono text-xs" : ""}`}
        type={field.type === "number" ? "number" : "text"}
        placeholder={field.placeholder}
        value={value}
        onChange={(e) => {
          if (field.id === "port") {
            onChange({ port: Number(e.target.value) });
            return;
          }
          onChange({ [field.id]: e.target.value } as Partial<DbConnectionPayload>);
        }}
      />
    </div>
  );
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
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: connectors } = useQuery({
    queryKey: ["warehouse-connectors"],
    queryFn: api.listWarehouseConnectors,
    staleTime: 60_000,
  });

  const selectedConnector = useMemo(
    () => warehouseConnectorById(connectors, form.warehouse_type),
    [connectors, form.warehouse_type],
  );

  useEffect(() => {
    if (!open) return;
    const next = connection ? connectionToForm(connection) : emptyForm();
    setForm(next);
    setInitialForm(next);
    setPassword("");
    setMessage(null);
    setError(null);
  }, [open, connection]);

  const updateForm = (patch: Partial<DbConnectionPayload>) => {
    setForm((prev) => {
      let next = { ...prev, ...patch };
      if (patch.warehouse_type && patch.warehouse_type !== prev.warehouse_type) {
        const defaults = defaultsForWarehouseType(connectors, patch.warehouse_type);
        next = {
          ...next,
          port: defaults.port,
          schema: defaults.schema || next.schema,
          database: defaults.database,
        };
      }
      if (!isEdit && patch.name !== undefined && !prev.catalog.trim()) {
        next.catalog = suggestCatalogName(patch.name);
      }
      return next;
    });
  };

  const payload = (): DbConnectionPayload => ({
    ...form,
    password: password || undefined,
  });

  const test = useMutation({
    mutationFn: () => api.testDbConnection(payload()),
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
      const body = payload();
      if (isEdit && connection) {
        return api.updateDbConnection(connection.id, body);
      }
      return api.createDbConnection(body);
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
  const formChanged = hasFormChanges(form, initialForm, isEdit, password);
  const formValid = isWarehouseFormValid(form, connectors);
  const passwordOk = isEdit ? connection?.password_set || password.length > 0 : password.length > 0;
  const canSave = formChanged && formValid && passwordOk && !nameTaken && !save.isPending;
  const canTest = formValid && passwordOk;
  const groups = connectors ? warehouseGroups(connectors) : [];

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="db-conn-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card modal-card--wide">
        <div className="modal-header">
          <h2 id="db-conn-title" className="text-lg font-semibold">
            {isEdit ? "Edit business connection" : "New business connection"}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Register a warehouse behind Trino. Choose the database type, then supply credentials — DATA Pro
          writes a Trino catalog file and uses it for structured datasets.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="field mb-0 sm:col-span-2">
            <label className="label">Connection name</label>
            <input
              className="input"
              placeholder="e.g. Finance_DB"
              value={form.name}
              onChange={(e) => updateForm({ name: e.target.value })}
            />
            {nameTaken && (
              <p className="alert-error mt-2 text-xs">This name is already used. Choose a unique name.</p>
            )}
          </div>
          <div className="field mb-0">
            <label className="label">Query engine</label>
            <input className="input" value="Trino" readOnly />
          </div>
          <div className="field mb-0">
            <label className="label">Warehouse type</label>
            <select
              className="select"
              value={form.warehouse_type}
              onChange={(e) => updateForm({ warehouse_type: e.target.value })}
            >
              {groups.map((group) => (
                <optgroup key={group} label={groupLabel(group)}>
                  {connectors
                    ?.filter((c) => c.group === group)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
            {selectedConnector?.description && (
              <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
                {selectedConnector.description}
              </p>
            )}
          </div>
          <div className="field mb-0">
            <label className="label">Trino catalog</label>
            <input
              className="input font-mono text-xs"
              placeholder="finance"
              value={form.catalog}
              onChange={(e) => updateForm({ catalog: e.target.value })}
            />
          </div>
          <div className="field mb-0">
            <label className="label">Default schema</label>
            <input
              className="input font-mono text-xs"
              placeholder="finance_data"
              value={form.schema}
              onChange={(e) => updateForm({ schema: e.target.value })}
            />
          </div>
          {selectedConnector?.fields.map((field) => (
            <ConnectorField
              key={field.id}
              field={field}
              form={form}
              password={password}
              passwordSet={connection?.password_set}
              onPasswordChange={setPassword}
              onChange={updateForm}
            />
          ))}
        </div>
        {message && <p className="alert-ok mt-3">{message}</p>}
        {error && <p className="alert-error mt-3">{error}</p>}
        <div className="modal-actions modal-actions--split">
          <button type="button" className="btn" disabled={!canSave} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          <div className="modal-actions-end">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!canTest || test.isPending}
              onClick={() => test.mutate()}
            >
              {test.isPending ? "Testing…" : "Test connection"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
