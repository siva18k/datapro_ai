import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { devBootstrap, isDevBootstrapAvailable, type DevBootstrapResponse } from "../api/devBootstrap";

const AUTO_START_WAIT_MS = 5000;
const MANUAL_START_WAIT_MS = 10000;
const POLL_INTERVAL_MS = 500;
const BACKGROUND_PING_MS = 30_000;

export type ApiBootstrapPhase = "checking" | "starting" | "online" | "offline" | "error";

type ApiConnectionContextValue = {
  apiOnline: boolean;
  bootstrapPhase: ApiBootstrapPhase;
  bootstrapMessage: string | null;
  starting: boolean;
  showStartButton: boolean;
  canStartFromWeb: boolean;
  lastChecked: Date | null;
  refresh: () => Promise<boolean>;
  startApiServer: () => Promise<DevBootstrapResponse>;
  retryConnection: () => Promise<boolean>;
};

const ApiConnectionContext = createContext<ApiConnectionContextValue | null>(null);

async function pingApi(timeoutMs = 2000): Promise<boolean> {
  try {
    const res = await fetch("/api/health", { signal: AbortSignal.timeout(timeoutMs) });
    return res.ok;
  } catch {
    return false;
  }
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
}

export function ApiConnectionProvider({ children }: { children: ReactNode }) {
  const canStartFromWeb = isDevBootstrapAvailable();
  const [apiOnline, setApiOnline] = useState(false);
  const [bootstrapPhase, setBootstrapPhase] = useState<ApiBootstrapPhase>("checking");
  const [bootstrapMessage, setBootstrapMessage] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const bootstrapRan = useRef(false);
  const startingRef = useRef(false);

  const markOnline = useCallback(() => {
    setApiOnline(true);
    setBootstrapPhase("online");
    setBootstrapMessage(null);
    setLastChecked(new Date());
  }, []);

  const markOffline = useCallback((message: string | null = null) => {
    setApiOnline(false);
    setBootstrapPhase("offline");
    setBootstrapMessage(message);
    setLastChecked(new Date());
  }, []);

  const pollUntilOnline = useCallback(async (timeoutMs: number) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await pingApi()) {
        markOnline();
        return true;
      }
      await sleep(POLL_INTERVAL_MS);
    }
    setLastChecked(new Date());
    return false;
  }, [markOnline]);

  const refresh = useCallback(async () => {
    const ok = await pingApi();
    setApiOnline(ok);
    setLastChecked(new Date());
    if (ok) {
      setBootstrapPhase("online");
      setBootstrapMessage(null);
    } else if (!startingRef.current) {
      setBootstrapPhase(canStartFromWeb ? "offline" : "error");
      if (!canStartFromWeb) {
        setBootstrapMessage("Run uvicorn on port 8080.");
      }
    }
    return ok;
  }, [canStartFromWeb]);

  const startApiServer = useCallback(async (): Promise<DevBootstrapResponse> => {
    if (!canStartFromWeb) {
      const message = "Start the API from the terminal (uvicorn on port 8080).";
      setBootstrapPhase("error");
      setBootstrapMessage(message);
      return {
        ok: false,
        message,
        reachable: false,
        url: "http://127.0.0.1:8080",
        port: 8080,
        managed: false,
      };
    }

    startingRef.current = true;
    setBootstrapPhase("starting");
    setBootstrapMessage("Starting API server…");

    try {
      const res = await devBootstrap.startApi();
      if (res.reachable) {
        markOnline();
        return { ...res, ok: true, reachable: true };
      }

      const online = await pollUntilOnline(MANUAL_START_WAIT_MS);
      if (online) {
        return { ...res, ok: true, reachable: true };
      }

      const message =
        res.message ||
        "API server did not respond in time. Check .api_server.log or try again.";
      markOffline(message);
      return { ...res, ok: false, reachable: false, message };
    } catch (err) {
      const message =
        err instanceof Error && !(err instanceof SyntaxError)
          ? err.message
          : "Could not start the API server. Check .api_server.log or try again.";
      setBootstrapPhase("error");
      setBootstrapMessage(message);
      setApiOnline(false);
      setLastChecked(new Date());
      return {
        ok: false,
        message,
        reachable: false,
        url: "http://127.0.0.1:8080",
        port: 8080,
        managed: false,
      };
    } finally {
      startingRef.current = false;
    }
  }, [canStartFromWeb, markOnline, markOffline, pollUntilOnline]);

  const retryConnection = useCallback(async () => {
    setBootstrapPhase("starting");
    setBootstrapMessage("Checking API connection…");
    const online = await pollUntilOnline(AUTO_START_WAIT_MS);
    if (!online) {
      markOffline("API server is not reachable.");
    }
    return online;
  }, [markOffline, pollUntilOnline]);

  useEffect(() => {
    if (bootstrapRan.current) return;
    bootstrapRan.current = true;

    void (async () => {
      if (await pingApi()) {
        markOnline();
        return;
      }

      if (!canStartFromWeb) {
        markOffline("Run uvicorn on port 8080.");
        return;
      }

      setBootstrapPhase("starting");
      setBootstrapMessage("Starting API server…");

      const online = await pollUntilOnline(AUTO_START_WAIT_MS);
      if (online) return;

      try {
        const res = await devBootstrap.startApi();
        if (res.reachable) {
          markOnline();
          return;
        }
        if (await pollUntilOnline(2000)) return;

        markOffline(
          res.message || "API server is not running. Press Start API server below.",
        );
      } catch (err) {
        setBootstrapPhase("error");
        setBootstrapMessage(err instanceof Error ? err.message : String(err));
        setApiOnline(false);
        setLastChecked(new Date());
      }
    })();
  }, [canStartFromWeb, markOffline, markOnline, pollUntilOnline]);

  useEffect(() => {
    if (!apiOnline) return;
    const id = window.setInterval(() => {
      if (startingRef.current) return;
      void pingApi().then((ok) => {
        setLastChecked(new Date());
        if (ok) return;
        setApiOnline(false);
        setBootstrapPhase(canStartFromWeb ? "offline" : "error");
        setBootstrapMessage("API server stopped responding.");
      });
    }, BACKGROUND_PING_MS);
    return () => window.clearInterval(id);
  }, [apiOnline, canStartFromWeb]);

  const starting = bootstrapPhase === "starting";
  const showStartButton =
    canStartFromWeb && !apiOnline && (bootstrapPhase === "offline" || bootstrapPhase === "error");

  const value = useMemo(
    () => ({
      apiOnline,
      bootstrapPhase,
      bootstrapMessage,
      starting,
      showStartButton,
      canStartFromWeb,
      lastChecked,
      refresh,
      startApiServer,
      retryConnection,
    }),
    [
      apiOnline,
      bootstrapPhase,
      bootstrapMessage,
      starting,
      showStartButton,
      canStartFromWeb,
      lastChecked,
      refresh,
      startApiServer,
      retryConnection,
    ],
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
  const { apiOnline, bootstrapPhase, bootstrapMessage, starting } = useApiConnection();
  return {
    apiOnline,
    apiPending: bootstrapPhase === "checking" || starting,
    showConnecting: starting,
    showOffline: !apiOnline && (bootstrapPhase === "offline" || bootstrapPhase === "error"),
    connectingTitle: bootstrapMessage ?? "Starting API server…",
  };
}
