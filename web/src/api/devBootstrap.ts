export type DevBootstrapResponse = {
  ok: boolean;
  message: string;
  reachable: boolean;
  url: string;
  port: number;
  managed: boolean;
};

const PREFIX = "/__datapro/dev";

function parseBootstrapJson(text: string): DevBootstrapResponse {
  if (!text.trim()) {
    throw new Error(
      "Empty response from dev server — Vite may still be starting. Wait a moment and try again.",
    );
  }
  try {
    return JSON.parse(text) as DevBootstrapResponse;
  } catch {
    throw new Error("Invalid response from dev server — try Start API server again.");
  }
}

async function devRequest(path: string, method: "GET" | "POST" = "GET"): Promise<DevBootstrapResponse> {
  let res: Response;
  try {
    res = await fetch(`${PREFIX}${path}`, { method });
  } catch {
    throw new Error("Could not reach the Vite dev server. Run npm run dev from the web folder.");
  }
  const text = await res.text();
  if (!res.ok) {
    if (!text.trim()) {
      throw new Error(`Dev bootstrap failed (${res.status}). Is npm run dev still running?`);
    }
    try {
      return parseBootstrapJson(text);
    } catch (e) {
      if (e instanceof Error && !(e instanceof SyntaxError)) throw e;
      throw new Error(text.slice(0, 200) || `Dev bootstrap failed (${res.status}).`);
    }
  }
  return parseBootstrapJson(text);
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
