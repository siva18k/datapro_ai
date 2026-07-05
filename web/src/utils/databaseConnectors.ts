/** Trino-backed business dataset connections. */

export const TRINO_CONNECTOR = "trino";

export function suggestCatalogName(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!slug) return "warehouse";
  return /^[0-9]/.test(slug) ? `c_${slug}` : slug;
}

export function trinoCatalogLabel(catalog?: string): string {
  const value = catalog?.trim();
  return value ? `Trino (${value})` : "Trino";
}
