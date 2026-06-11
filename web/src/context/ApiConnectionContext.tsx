import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type ApiConnectionContextValue = {
  apiOnline: boolean;
  checking: boolean;
  lastChecked: Date | null;
  refresh: () => Promise<boolean>;
};

const ApiConnectionContext = createContext<ApiConnectionContextValue | null>(null);

async function pingApi(): Promise<boolean> {
  try {
    const res = await fetch("/api/health", { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}

export function ApiConnectionProvider({ children }: { children: ReactNode }) {
  const [apiOnline, setApiOnline] = useState(false);
  const [checking, setChecking] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setChecking(true);
    const ok = await pingApi();
    setApiOnline(ok);
    setLastChecked(new Date());
    setChecking(false);
    return ok;
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const value = useMemo(
    () => ({ apiOnline, checking, lastChecked, refresh }),
    [apiOnline, checking, lastChecked, refresh],
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
