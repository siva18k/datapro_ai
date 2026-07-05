import { dbConnectionDisplayFields } from "../utils/dbConnectionDisplay";

export function DbConnectionSummary({
  user,
  schema,
  databaseType,
  warehouseTypeLabel,
  connector,
  catalog,
  host,
  database,
  snowflakeAccount,
  userFallback,
  className = "",
}: {
  user?: string;
  schema?: string;
  databaseType?: string;
  warehouseTypeLabel?: string;
  connector?: string;
  catalog?: string;
  host?: string;
  database?: string;
  snowflakeAccount?: string;
  userFallback?: string;
  className?: string;
}) {
  const fields = dbConnectionDisplayFields({
    user,
    schema,
    databaseType,
    warehouseTypeLabel,
    connector,
    catalog,
    userFallback,
  });
  const endpoint = snowflakeAccount?.trim()
    ? snowflakeAccount.trim()
    : host?.trim()
      ? `${host.trim()}${database?.trim() ? ` / ${database.trim()}` : ""}`
      : null;

  return (
    <dl className={`db-connection-summary ${className}`.trim()}>
      <div className="db-connection-summary-row">
        <dt>Engine</dt>
        <dd>{fields.databaseType}</dd>
      </div>
      {endpoint && (
        <div className="db-connection-summary-row">
          <dt>Host</dt>
          <dd className="font-mono text-xs">{endpoint}</dd>
        </div>
      )}
      <div className="db-connection-summary-row">
        <dt>Schema</dt>
        <dd>{fields.schema}</dd>
      </div>
      <div className="db-connection-summary-row">
        <dt>User</dt>
        <dd>{fields.user}</dd>
      </div>
    </dl>
  );
}
