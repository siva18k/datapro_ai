import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AskPipelineSteps } from "../components/AskPipelineSteps";
import {
  loadPipelineTraceSession,
  subscribePipelineTraceSession,
  type PipelineTraceSession,
} from "../utils/pipelineTraceSession";

export function AskDebugPage() {
  const [session, setSession] = useState<PipelineTraceSession | null>(() =>
    loadPipelineTraceSession(),
  );

  useEffect(() => {
    return subscribePipelineTraceSession(setSession);
  }, []);

  useEffect(() => {
    const refresh = () => setSession(loadPipelineTraceSession());
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  const steps = session?.steps ?? [];
  const isActive = session?.isActive ?? false;

  return (
    <div className="ask-debug-page">
      <header className="ask-debug-header">
        <div>
          <h1 className="ask-debug-title">Pipeline trace</h1>
          <p className="ask-debug-subtitle">
            Live debug view — updates while Ask runs with Debug enabled
          </p>
        </div>
        <Link to="/ask" className="btn btn-secondary btn-sm">
          Back to Ask
        </Link>
      </header>

      {steps.length === 0 ? (
        <div className="ask-debug-empty card card-pad">
          <p className="font-medium">No trace yet</p>
          <p className="mt-2 text-sm" style={{ color: "var(--color-text-muted)" }}>
            Enable <strong>Debug</strong> on the Ask page, run a question, then open this tab
            from the pipeline panel — or keep this tab open during a run for live updates.
          </p>
          <Link to="/ask" className="btn btn-primary btn-sm mt-4 inline-flex">
            Go to Ask
          </Link>
        </div>
      ) : (
        <div className="ask-debug-panel">
          <AskPipelineSteps steps={steps} isActive={isActive} standalone />
        </div>
      )}

      {session?.updatedAt && (
        <p className="ask-debug-updated">
          Last updated {new Date(session.updatedAt).toLocaleTimeString()}
          {isActive && " · streaming"}
        </p>
      )}
    </div>
  );
}
