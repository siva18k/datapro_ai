export type DevBootstrapResponse = {
  ok: boolean;
  message: string;
  reachable: boolean;
  url: string;
  port: number;
  managed: boolean;
};

const PREFIX = "/__datapro/dev";

async function devRequest(path: string, method: "GET" | "POST" = "GET"): Promise<DevBootstrapResponse> {
  const res = await fetch(`${PREFIX}${path}`, { method });
  return res.json() as Promise<DevBootstrapResponse>;
}

export const devBootstrap = {
  apiStatus: () => devRequest("/api/status"),
  startApi: () => devRequest("/api/start", "POST"),
  stopApi: () => devRequest("/api/stop", "POST"),
  restartApi: () => devRequest("/api/restart", "POST"),
};

/** True when Vite dev bootstrap routes are available (local dev, not production build). */
export function isDevBootstrapAvailable(): boolean {
  return import.meta.env.DEV;
}
