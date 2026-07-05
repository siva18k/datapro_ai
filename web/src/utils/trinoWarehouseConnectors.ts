import type { DbConnectionPayload, WarehouseConnectorDefinition } from "../api/client";

export const DEFAULT_WAREHOUSE_TYPE = "postgresql";

export function warehouseConnectorById(
  connectors: WarehouseConnectorDefinition[] | undefined,
  id: string,
): WarehouseConnectorDefinition | undefined {
  return connectors?.find((c) => c.id === id);
}

export function defaultsForWarehouseType(
  connectors: WarehouseConnectorDefinition[] | undefined,
  warehouseType: string,
): Pick<DbConnectionPayload, "port" | "schema" | "database"> {
  const def = warehouseConnectorById(connectors, warehouseType);
  return {
    port: def?.default_port || 5432,
    schema: def?.default_schema || "public",
    database: def?.default_database || "",
  };
}

export function fieldValue(form: DbConnectionPayload, fieldId: string): string {
  const extra = form.extra ?? {};
  const top = form[fieldId as keyof DbConnectionPayload];
  if (typeof top === "string" && top.trim()) return top;
  if (typeof top === "number" && fieldId === "port") return String(top);
  return extra[fieldId]?.trim() ?? "";
}

export function isWarehouseFormValid(
  form: DbConnectionPayload,
  connectors: WarehouseConnectorDefinition[] | undefined,
): boolean {
  if (!form.name.trim() || !form.schema.trim()) return false;
  if (form.connector === "postgres") {
    if (!form.host?.trim() || !String(form.port ?? "").trim() || !form.database?.trim() || !form.user?.trim()) {
      return false;
    }
    return true;
  }
  if (!form.catalog.trim()) return false;
  const def = warehouseConnectorById(connectors, form.warehouse_type);
  if (!def) return false;
  for (const field of def.fields) {
    if (field.id === "password") continue;
    if (!field.required) continue;
    if (!fieldValue(form, field.id)) return false;
  }
  return true;
}

export function warehouseGroups(connectors: WarehouseConnectorDefinition[]): string[] {
  const seen = new Set<string>();
  const groups: string[] = [];
  for (const c of connectors) {
    if (!seen.has(c.group)) {
      seen.add(c.group);
      groups.push(c.group);
    }
  }
  return groups;
}

export function groupLabel(group: string): string {
  switch (group) {
    case "relational":
      return "Relational databases";
    case "cloud":
      return "Cloud warehouses";
    case "analytics":
      return "Analytics";
    case "advanced":
      return "Advanced";
    default:
      return group;
  }
}
