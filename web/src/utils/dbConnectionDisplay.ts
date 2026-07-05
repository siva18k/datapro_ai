import { trinoCatalogLabel } from "./databaseConnectors";

export interface DbConnectionDisplayFields {
  databaseType: string;
  schema: string;
  user: string;
}

export function dbConnectionDisplayFields(opts: {
  user?: string;
  schema?: string;
  databaseType?: string;
  warehouseTypeLabel?: string;
  connector?: string;
  catalog?: string;
  userFallback?: string;
}): DbConnectionDisplayFields {
  const user = opts.user?.trim() || opts.userFallback?.trim() || "—";
  const databaseType =
    opts.warehouseTypeLabel?.trim() ||
    opts.databaseType?.trim() ||
    (opts.connector === "postgres"
      ? "PostgreSQL"
      : opts.catalog
        ? trinoCatalogLabel(opts.catalog)
        : "Trino");
  return {
    databaseType,
    schema: opts.schema?.trim() || "—",
    user,
  };
}
