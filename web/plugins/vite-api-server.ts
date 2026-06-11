import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Connect, Plugin } from "vite";

const API_HOST = "127.0.0.1";
const API_PORT = 8080;
const BOOTSTRAP_PREFIX = "/__datapro/dev";

type BootstrapAction = {
  ok: boolean;
  message: string;
  reachable: boolean;
  url: string;
  port: number;
  managed: boolean;
};

async function isApiReachable(): Promise<boolean> {
  try {
    const res = await fetch(`http://${API_HOST}:${API_PORT}/api/health`, {
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function resolvePython(projectRoot: string): string {
  const venvPython = path.join(projectRoot, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) return venvPython;
  return process.platform === "win32" ? "python" : "python3";
}

function sendJson(res: Connect.ServerResponse, status: number, body: BootstrapAction) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

function readBody(req: Connect.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

export function apiServerPlugin(): Plugin {
  let proc: ChildProcessWithoutNullStreams | null = null;
  let managed = false;
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
  const logPath = path.join(projectRoot, ".api_server.log");

  const statusPayload = async (): Promise<BootstrapAction> => {
    const reachable = await isApiReachable();
    return {
      ok: reachable,
      message: reachable
        ? `API server reachable at http://${API_HOST}:${API_PORT}`
        : "API server is not running.",
      reachable,
      url: `http://${API_HOST}:${API_PORT}`,
      port: API_PORT,
      managed: managed && proc != null && !proc.killed,
    };
  };

  const startApi = async (): Promise<BootstrapAction> => {
    if (await isApiReachable()) {
      return {
        ok: false,
        message: `API server already running at http://${API_HOST}:${API_PORT}`,
        reachable: true,
        url: `http://${API_HOST}:${API_PORT}`,
        port: API_PORT,
        managed: managed && proc != null && !proc.killed,
      };
    }

    if (proc && !proc.killed) {
      return statusPayload();
    }

    const python = resolvePython(projectRoot);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    const logHandle = fs.openSync(logPath, "a");
    fs.writeSync(logHandle, `\n--- vite bootstrap start ${new Date().toISOString()} ---\n`);

    proc = spawn(
      python,
      ["-m", "uvicorn", "api.main:app", "--reload", "--host", API_HOST, "--port", String(API_PORT)],
      {
        cwd: projectRoot,
        env: { ...process.env, API_HOST, API_PORT: String(API_PORT) },
        detached: false,
        stdio: ["ignore", logHandle, logHandle],
      },
    );
    managed = true;

    proc.on("exit", () => {
      proc = null;
      managed = false;
    });

    proc.on("error", (err) => {
      console.error("[datapro] Failed to start API server:", err.message);
      proc = null;
      managed = false;
    });

    for (let attempt = 0; attempt < 40; attempt += 1) {
      if (await isApiReachable()) {
        console.log(`[datapro] API started from web at http://${API_HOST}:${API_PORT}`);
        return {
          ok: true,
          message: `Started API server at http://${API_HOST}:${API_PORT}`,
          reachable: true,
          url: `http://${API_HOST}:${API_PORT}`,
          port: API_PORT,
          managed: true,
        };
      }
      if (proc.exitCode != null) {
        return {
          ok: false,
          message: `API server exited early (code ${proc.exitCode}). Check ${logPath}`,
          reachable: false,
          url: `http://${API_HOST}:${API_PORT}`,
          port: API_PORT,
          managed: false,
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }

    return {
      ok: false,
      message: "API process started but is not reachable yet. Try Retry in a few seconds.",
      reachable: false,
      url: `http://${API_HOST}:${API_PORT}`,
      port: API_PORT,
      managed: true,
    };
  };

  const stopApi = async (): Promise<BootstrapAction> => {
    if (proc && !proc.killed) {
      proc.kill("SIGTERM");
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (proc && !proc.killed) proc.kill("SIGKILL");
      proc = null;
      managed = false;
      return {
        ok: true,
        message: "Stopped API server.",
        reachable: await isApiReachable(),
        url: `http://${API_HOST}:${API_PORT}`,
        port: API_PORT,
        managed: false,
      };
    }

    if (!(await isApiReachable())) {
      return {
        ok: false,
        message: "API server is not running.",
        reachable: false,
        url: `http://${API_HOST}:${API_PORT}`,
        port: API_PORT,
        managed: false,
      };
    }

    return {
      ok: false,
      message:
        "API server is running but was not started from this dev session. Stop it from Settings or your terminal.",
      reachable: true,
      url: `http://${API_HOST}:${API_PORT}`,
      port: API_PORT,
      managed: false,
    };
  };

  return {
    name: "datapro-api-server",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url?.split("?")[0] ?? "";
        if (!url.startsWith(BOOTSTRAP_PREFIX)) {
          next();
          return;
        }

        try {
          if (url === `${BOOTSTRAP_PREFIX}/api/status` && req.method === "GET") {
            sendJson(res, 200, await statusPayload());
            return;
          }

          if (url === `${BOOTSTRAP_PREFIX}/api/start` && req.method === "POST") {
            await readBody(req);
            sendJson(res, 200, await startApi());
            return;
          }

          if (url === `${BOOTSTRAP_PREFIX}/api/stop` && req.method === "POST") {
            await readBody(req);
            sendJson(res, 200, await stopApi());
            return;
          }

          if (url === `${BOOTSTRAP_PREFIX}/api/restart` && req.method === "POST") {
            await readBody(req);
            await stopApi();
            await new Promise((resolve) => setTimeout(resolve, 500));
            sendJson(res, 200, await startApi());
            return;
          }

          sendJson(res, 404, {
            ok: false,
            message: "Not found",
            reachable: await isApiReachable(),
            url: `http://${API_HOST}:${API_PORT}`,
            port: API_PORT,
            managed: false,
          });
        } catch (err) {
          sendJson(res, 500, {
            ok: false,
            message: err instanceof Error ? err.message : "Bootstrap error",
            reachable: false,
            url: `http://${API_HOST}:${API_PORT}`,
            port: API_PORT,
            managed: false,
          });
        }
      });

      console.log(
        `[datapro] Dev bootstrap ready — start API from Settings (${BOOTSTRAP_PREFIX}/api/start)`,
      );

      return () => {
        if (managed && proc && !proc.killed) {
          proc.kill("SIGTERM");
        }
      };
    },
  };
}
