import type { PipelineTraceStep } from "../types";

/** Shared across tabs via localStorage (sessionStorage is not visible to noopener popups). */
export const PIPELINE_TRACE_SESSION_KEY = "datapro-pipeline-trace";

export interface PipelineTraceSession {
  steps: PipelineTraceStep[];
  isActive: boolean;
  updatedAt: number;
}

function traceStorage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

export function savePipelineTraceSession(data: PipelineTraceSession): void {
  try {
    traceStorage()?.setItem(PIPELINE_TRACE_SESSION_KEY, JSON.stringify(data));
  } catch {
    /* quota or private mode */
  }
}

export function loadPipelineTraceSession(): PipelineTraceSession | null {
  try {
    const raw = traceStorage()?.getItem(PIPELINE_TRACE_SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PipelineTraceSession;
  } catch {
    return null;
  }
}

export function clearPipelineTraceSession(): void {
  try {
    traceStorage()?.removeItem(PIPELINE_TRACE_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function subscribePipelineTraceSession(
  onUpdate: (data: PipelineTraceSession | null) => void,
): () => void {
  const handler = (event: StorageEvent) => {
    if (event.key === PIPELINE_TRACE_SESSION_KEY) {
      onUpdate(loadPipelineTraceSession());
    }
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

export function openPipelineTraceTab(steps: PipelineTraceStep[], isActive: boolean): void {
  savePipelineTraceSession({ steps, isActive, updatedAt: Date.now() });
  window.open(`${window.location.origin}/ask/debug`, "_blank", "noopener,noreferrer");
}
