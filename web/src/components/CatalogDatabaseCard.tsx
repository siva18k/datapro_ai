import type { DatabaseSettingsPayload } from "../api/client";
import { DbConnectionSummary } from "./DbConnectionSummary";

export interface CatalogDatabaseCardProps {
  db: DatabaseSettingsPayload;
  passwordSet: boolean;
  configured: boolean;
  editing: boolean;
  userFallback?: string;
  urlPaste: string;
  urlPasteError: string | null;
  notice: { ok: boolean; text: string } | null;
  testing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onUpdateDb: (patch: Partial<DatabaseSettingsPayload>) => void;
  onUrlPasteChange: (value: string) => void;
  onApplyUrlPaste: () => void;
  onTest: () => void;
}

export function CatalogDatabaseCard({
  db,
  passwordSet,
  configured,
  editing,
  userFallback,
  urlPaste,
  urlPasteError,
  notice,
  testing,
  onEdit,
  onCancel,
  onUpdateDb,
  onUrlPasteChange,
  onApplyUrlPaste,
  onTest,
}: CatalogDatabaseCardProps) {
  return (
    <li
      className={`saved-connection-card saved-connection-card--catalog${
        editing ? " saved-connection-card--editing" : ""
      }`}
    >
      <div className="saved-connection-card-header">
        <div className="min-w-0">
          <p className="saved-connection-card-name">Catalog database</p>
          <p className="saved-connection-card-desc">
            Base Postgres for catalog metadata &amp; RAG vectors
          </p>
        </div>
        <span className="saved-connection-card-badge saved-connection-card-badge--required">
          Required
        </span>
      </div>

      {!editing ? (
        <>
          {configured ? (
            <DbConnectionSummary user={db.user} schema={db.schema} connector="postgres" userFallback={userFallback} />
          ) : (
            <p className="saved-connection-card-meta">Not configured</p>
          )}
          <p className="saved-connection-card-meta">
            SSL: {db.sslmode}
            {passwordSet ? " · Password set" : ""}
          </p>
          <div className="saved-connection-card-actions">
            <button type="button" className="btn-ghost btn-sm" onClick={onEdit}>
              Edit
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm"
              disabled={testing || !configured}
              onClick={onTest}
            >
              {testing ? "Testing…" : "Test connection"}
            </button>
          </div>
          {notice && (
            <p className={notice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{notice.text}</p>
          )}
        </>
      ) : (
        <div className="saved-connection-card-form space-y-4">
          <div className="field mb-0">
            <label className="label" htmlFor="catalog-db-url-paste">
              Connection URL (optional)
            </label>
            <div className="flex flex-wrap gap-2">
              <input
                id="catalog-db-url-paste"
                className="input min-w-0 flex-1 font-mono text-xs"
                placeholder="postgresql://user:pass@host:5432/database?sslmode=require"
                value={urlPaste}
                onChange={(e) => onUrlPasteChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    onApplyUrlPaste();
                  }
                }}
              />
              <button type="button" className="btn btn-secondary btn-sm shrink-0" onClick={onApplyUrlPaste}>
                Apply URL
              </button>
            </div>
            <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
              Paste a full Postgres URL to fill the fields below.
            </p>
            {urlPasteError && <p className="alert-error mt-2 text-xs">{urlPasteError}</p>}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="field mb-0 sm:col-span-2">
              <label className="label">Host / endpoint</label>
              <input className="input" value={db.host} onChange={(e) => onUpdateDb({ host: e.target.value })} />
            </div>
            <div className="field mb-0">
              <label className="label">Port</label>
              <input
                className="input"
                type="number"
                value={db.port}
                onChange={(e) => onUpdateDb({ port: Number(e.target.value) })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">SSL mode</label>
              <select
                className="select"
                value={db.sslmode}
                onChange={(e) => onUpdateDb({ sslmode: e.target.value })}
              >
                <option value="require">require</option>
                <option value="verify-full">verify-full</option>
                <option value="prefer">prefer</option>
                <option value="disable">disable</option>
              </select>
            </div>
            <div className="field mb-0">
              <label className="label">Username</label>
              <input className="input" value={db.user} onChange={(e) => onUpdateDb({ user: e.target.value })} />
            </div>
            <div className="field mb-0">
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                placeholder={passwordSet ? "Leave blank to keep current password" : ""}
                value={db.password}
                onChange={(e) => onUpdateDb({ password: e.target.value })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Database</label>
              <input
                className="input"
                value={db.database}
                onChange={(e) => onUpdateDb({ database: e.target.value })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Schema</label>
              <input className="input" value={db.schema} onChange={(e) => onUpdateDb({ schema: e.target.value })} />
            </div>
          </div>

          <div className="saved-connection-card-actions">
            <button type="button" className="btn btn-secondary btn-sm" disabled={testing} onClick={onTest}>
              {testing ? "Testing…" : "Test connection"}
            </button>
            {configured && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
                Cancel
              </button>
            )}
          </div>
          {notice && (
            <p className={notice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{notice.text}</p>
          )}
        </div>
      )}
    </li>
  );
}
