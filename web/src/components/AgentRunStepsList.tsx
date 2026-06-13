import type { AgentRunStep } from "../types";

type Props = {
  steps: AgentRunStep[];
};

export function AgentRunStepsList({ steps }: Props) {
  return (
    <ol className="agent-run-steps space-y-2">
      {steps.map((step) => (
        <li
          key={step.step_id}
          className={`agent-run-step agent-run-step--${step.status || "ok"}`}
        >
          <span className="agent-run-step-id">{step.step_id}</span>
          {step.step_id === "plan" && step.payload?.plan != null ? (
            <details className="agent-run-plan-details">
              <summary className="agent-run-plan-summary">{step.message}</summary>
              <pre className="agent-run-plan-body whitespace-pre-wrap text-xs text-zinc-600">
                {String(step.payload.plan)}
              </pre>
            </details>
          ) : (
            <span>{step.message}</span>
          )}
        </li>
      ))}
    </ol>
  );
}
