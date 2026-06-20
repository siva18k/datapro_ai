import type { DatabaseSettingsPayload } from "../api/client";

export function parsePostgresUrl(input: string): Partial<DatabaseSettingsPayload> | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const normalized = trimmed.replace(/^postgres(ql)?:\/\//i, "https://");
    const url = new URL(normalized);
    const sslmode = url.searchParams.get("sslmode") ?? undefined;

    return {
      host: url.hostname,
      port: url.port ? Number(url.port) : 5432,
      user: decodeURIComponent(url.username),
      password: decodeURIComponent(url.password),
      database: url.pathname.replace(/^\//, "") || "postgres",
      sslmode: sslmode || "require",
      use_database_url: false,
      database_url: "",
    };
  } catch {
    return null;
  }
}

export function buildPostgresUrl(db: Pick<DatabaseSettingsPayload, "user" | "password" | "host" | "port" | "database" | "sslmode">): string {
  const user = encodeURIComponent(db.user);
  const password = encodeURIComponent(db.password);
  const auth = password ? `${user}:${password}` : user;
  const base = `postgresql://${auth}@${db.host}:${db.port}/${db.database}`;
  if (db.sslmode && db.sslmode !== "require") {
    return `${base}?sslmode=${encodeURIComponent(db.sslmode)}`;
  }
  return base;
}
