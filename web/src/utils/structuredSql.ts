export const STRUCTURED_SQL_CONNECTORS = new Set(["trino", "postgres"]);

export function isStructuredSqlConnector(connector: string | undefined): boolean {
  return STRUCTURED_SQL_CONNECTORS.has((connector || "").trim().toLowerCase());
}
