import { useMutation } from "@tanstack/react-query";
import { api, type TrinoSettingsPayload } from "../api/client";

function trinoEndpoint(form: TrinoSettingsPayload): string {
  const host = form.host?.trim() || "—";
  const port = form.port ?? 8081;
  return `${host}:${port}`;
}

export function TrinoServerCard({
  form,
  password,
  passwordSet,
  configured,
  editing,
  notice,
  onEdit,
  onCancel,
  onChange,
  onPasswordChange,
  onNotice,
}: {
  form: TrinoSettingsPayload;
  password: string;
  passwordSet: boolean;
  configured: boolean;
  editing: boolean;
  notice: { ok: boolean; text: string } | null;
  onEdit: () => void;
  onCancel: () => void;
  onChange: (patch: Partial<TrinoSettingsPayload>) => void;
  onPasswordChange: (value: string) => void;
  onNotice: (notice: { ok: boolean; text: string } | null) => void;
}) {
  const test = useMutation({
    mutationFn: () =>
      api.testTrinoServer({
        ...form,
        password: password || undefined,
      }),
    onMutate: () => onNotice(null),
    onSuccess: (res) => onNotice({ ok: true, text: res.message }),
    onError: (err) => onNotice({ ok: false, text: String(err) }),
  });

  return (
    <li
      className={`saved-connection-card saved-connection-card--trino-server${
        editing ? " saved-connection-card--editing" : ""
      }`}
    >
      <div className="saved-connection-card-header">
        <div className="min-w-0">
          <p className="saved-connection-card-name">Trino coordinator</p>
          <p className="saved-connection-card-desc">
            Query engine for all business datasets. Catalog credentials are configured on the Trino server.
          </p>
        </div>
        <span className="saved-connection-card-badge saved-connection-card-badge--required">Required</span>
      </div>

      {!editing ? (
        <>
          {configured ? (
            <dl className="db-connection-summary">
              <div className="db-connection-summary-row">
                <dt>Host</dt>
                <dd className="font-mono text-xs">{trinoEndpoint(form)}</dd>
              </div>
              <div className="db-connection-summary-row">
                <dt>User</dt>
                <dd>{form.user?.trim() || "—"}</dd>
              </div>
              <div className="db-connection-summary-row">
                <dt>Scheme</dt>
                <dd>{form.http_scheme || "http"}</dd>
              </div>
            </dl>
          ) : (
            <p className="saved-connection-card-meta">Not configured</p>
          )}
          <p className="saved-connection-card-meta">
            TLS verify: {form.verify_ssl ? "on" : "off"}
            {passwordSet ? " · Password set" : ""}
          </p>
          <div className="saved-connection-card-actions">
            <button type="button" className="btn-ghost btn-sm" onClick={onEdit}>
              Edit
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm"
              disabled={test.isPending || !configured}
              onClick={() => test.mutate()}
            >
              {test.isPending ? "Testing…" : "Test Trino"}
            </button>
          </div>
          {notice && (
            <p className={notice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{notice.text}</p>
          )}
        </>
      ) : (
        <div className="saved-connection-card-form space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="field mb-0 sm:col-span-2">
              <label className="label">Host</label>
              <input
                className="input font-mono text-xs"
                value={form.host}
                onChange={(e) => onChange({ host: e.target.value })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Port</label>
              <input
                className="input"
                type="number"
                value={form.port}
                onChange={(e) => onChange({ port: Number(e.target.value) })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">HTTP scheme</label>
              <select
                className="select"
                value={form.http_scheme}
                onChange={(e) => onChange({ http_scheme: e.target.value })}
              >
                <option value="http">http</option>
                <option value="https">https</option>
              </select>
            </div>
            <div className="field mb-0">
              <label className="label">User</label>
              <input
                className="input font-mono text-xs"
                value={form.user}
                onChange={(e) => onChange({ user: e.target.value })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Password</label>
              <input
                className="input"
                type="password"
                placeholder={passwordSet ? "Leave blank to keep current password" : ""}
                value={password}
                onChange={(e) => onPasswordChange(e.target.value)}
              />
            </div>
            <div className="field mb-0 flex items-end">
              <label className="checkbox-label text-sm">
                <input
                  type="checkbox"
                  checked={form.verify_ssl}
                  onChange={(e) => onChange({ verify_ssl: e.target.checked })}
                />
                Verify TLS certificate
              </label>
            </div>
          </div>
          <p className="saved-connection-card-meta">
            Docker: <code className="text-xs">trino:8080</code> · Host machine:{" "}
            <code className="text-xs">localhost:8081</code>
          </p>
          <div className="saved-connection-card-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={test.isPending}
              onClick={() => test.mutate()}
            >
              {test.isPending ? "Testing…" : "Test Trino"}
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
