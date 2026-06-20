import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type ApiConnectionContextValue = {
  apiOnline: boolean;
  checking: boolean;
  connecting: boolean;
  lastChecked: Date | null;
  refresh: () => Promise<boolean>;
  waitUntilOnline: (options?: { maxWaitMs?: number; intervalMs?: number }) => Promise<boolean>;
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
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const connectingRef = useRef(false);
  const apiOnlineRef = useRef(false);
  connectingRef.current = connecting;
  apiOnlineRef.current = apiOnline;

  const refresh = useCallback(async () => {
    if (connectingRef.current) return apiOnlineRef.current;
    setChecking(true);
    const ok = await pingApi();
    setApiOnline(ok);
    setLastChecked(new Date());
    setChecking(false);
    return ok;
  }, []);

  const waitUntilOnline = useCallback(async (options?: { maxWaitMs?: number; intervalMs?: number }) => {
    const maxWaitMs = options?.maxWaitMs ?? 20_000;
    const intervalMs = options?.intervalMs ?? 500;
    setConnecting(true);
    const deadline = Date.now() + maxWaitMs;
    let ok = false;
    while (Date.now() < deadline) {
      ok = await pingApi(2000);
      if (ok) {
        setApiOnline(true);
        setLastChecked(new Date());
        setConnecting(false);
        return true;
      }
      await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
    }
    setApiOnline(false);
    setLastChecked(new Date());
    setConnecting(false);
    return false;
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      if (!connectingRef.current) void refresh();
    }, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const value = useMemo(
    () => ({ apiOnline, checking, connecting, lastChecked, refresh, waitUntilOnline }),
    [apiOnline, checking, connecting, lastChecked, refresh, waitUntilOnline],
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
