import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { devBootstrap, type DevBootstrapResponse } from "../api/devBootstrap";

const USER_POLL_ATTEMPTS = 5;
const USER_POLL_INTERVAL_MS = 2000;

type ApiConnectionContextValue = {
  apiOnline: boolean;
  checking: boolean;
  connecting: boolean;
  starting: boolean;
  apiPending: boolean;
  lastChecked: Date | null;
  refresh: () => Promise<boolean>;
  waitUntilOnline: (options?: { maxAttempts?: number; intervalMs?: number }) => Promise<boolean>;
  retryConnection: () => Promise<boolean>;
  startApiServer: () => Promise<DevBootstrapResponse>;
};

const ApiConnectionContext = createContext<ApiConnectionContextValue | null>(null);

async function pingApi(timeoutMs = 3000): Promise<boolean> {
  try {
    const res = await fetch("/api/health", { signal: AbortSignal.timeout(timeoutMs) });
    return res.ok;
  } catch {
    return false;
  }
}

export function ApiConnectionProvider({ children }: { children: ReactNode }) {
  const [apiOnline, setApiOnline] = useState(false);
  const [checking, setChecking] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const connectingRef = useRef(false);
  const startingRef = useRef(false);
  const apiOnlineRef = useRef(false);
  connectingRef.current = connecting;
  startingRef.current = starting;
  apiOnlineRef.current = apiOnline;

  const isBusy = useCallback(() => connectingRef.current || startingRef.current, []);

  const refresh = useCallback(async () => {
    if (isBusy()) return apiOnlineRef.current;
    setChecking(true);
    const ok = await pingApi();
    setApiOnline(ok);
    setLastChecked(new Date());
    setChecking(false);
    return ok;
  }, [isBusy]);

  const waitUntilOnline = useCallback(async (options?: { maxAttempts?: number; intervalMs?: number }) => {
    const maxAttempts = options?.maxAttempts ?? USER_POLL_ATTEMPTS;
    const intervalMs = options?.intervalMs ?? USER_POLL_INTERVAL_MS;
    setConnecting(true);
    try {
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const ok = await pingApi(2000);
        if (ok) {
          setApiOnline(true);
          setLastChecked(new Date());
          return true;
        }
        if (attempt < maxAttempts - 1) {
          await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
        }
      }
      setApiOnline(false);
      setLastChecked(new Date());
      return false;
    } finally {
      setConnecting(false);
    }
  }, []);

  const retryConnection = useCallback(
    () => waitUntilOnline({ maxAttempts: USER_POLL_ATTEMPTS, intervalMs: USER_POLL_INTERVAL_MS }),
    [waitUntilOnline],
  );

  const startApiServer = useCallback(async (): Promise<DevBootstrapResponse> => {
    setStarting(true);
    try {
      const res = await devBootstrap.startApi();
      if (!res.ok && !res.managed && !res.reachable) {
        return res;
      }
      const online = await waitUntilOnline({
        maxAttempts: USER_POLL_ATTEMPTS,
        intervalMs: USER_POLL_INTERVAL_MS,
      });
      return { ...res, reachable: online, ok: online };
    } finally {
      setStarting(false);
    }
  }, [waitUntilOnline]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      if (!isBusy()) void refresh();
    }, 5000);
    return () => window.clearInterval(id);
  }, [refresh, isBusy]);

  const apiPending = checking || connecting || starting;

  const value = useMemo(
    () => ({
      apiOnline,
      checking,
      connecting,
      starting,
      apiPending,
      lastChecked,
      refresh,
      waitUntilOnline,
      retryConnection,
      startApiServer,
    }),
    [apiOnline, checking, connecting, starting, apiPending, lastChecked, refresh, waitUntilOnline, retryConnection, startApiServer],
  );

  return <ApiConnectionContext.Provider value={value}>{children}</ApiConnectionContext.Provider>;
}

export function useApiConnection() {
  const ctx = useContext(ApiConnectionContext);
  if (!ctx) {
    throw new Error("useApiConnection must be used within ApiConnectionProvider");
  }
  return ctx;
}

/** Gate page content while the API is still starting or being checked. */
export function useApiPageState() {
  const { apiOnline, apiPending, starting } = useApiConnection();
  return {
    apiOnline,
    apiPending,
    showConnecting: !apiOnline && apiPending,
    showOffline: !apiOnline && !apiPending,
    connectingTitle: starting ? "Starting API server…" : "Connecting to API server…",
  };
}
