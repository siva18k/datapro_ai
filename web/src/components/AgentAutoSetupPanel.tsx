import type { AgentCapabilities, AgentMcpKit, AgentToolBinding } from "../types";
import { AgentToolPicker } from "./AgentToolPicker";

type Props = {
  capabilities: AgentCapabilities;
  onCapabilitiesChange: (next: AgentCapabilities) => void;
  tools: AgentToolBinding[];
  onToolsChange: (next: AgentToolBinding[]) => void;
  disabled?: boolean;
  mcpKit?: AgentMcpKit | null;
};

export function AgentAutoSetupPanel({
  capabilities,
  onCapabilitiesChange,
  tools,
  onToolsChange,
  disabled = false,
  mcpKit = null,
}: Props) {
  return (
    <details className="agent-advanced-setup">
      <summary className="text-xs font-medium" style={{ color: "var(--color-text-muted)" }}>
        Advanced — override built-in steps, or add MCP abilities
      </summary>
      <fieldset className="field mb-0 mt-3">
        <legend className="label mb-2">Also do</legend>
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!capabilities.kpi_check}
              disabled={disabled}
              onChange={(e) =>
                onCapabilitiesChange({ ...capabilities, kpi_check: e.target.checked })
              }
            />
            Check numbers against rules in the instructions
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!capabilities.generate_report}
              disabled={disabled}
              onChange={(e) =>
                onCapabilitiesChange({ ...capabilities, generate_report: e.target.checked })
              }
            />
            Generate an HTML report
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!capabilities.send_email}
              disabled={disabled}
              onChange={(e) =>
                onCapabilitiesChange({ ...capabilities, send_email: e.target.checked })
              }
            />
            Prepare an email preview
          </label>
          {capabilities.send_email && (
            <div className="field mb-0 pl-6">
              <label className="label">Email to</label>
              <input
                className="input"
                value={capabilities.email_to || ""}
                disabled={disabled}
                onChange={(e) =>
                  onCapabilitiesChange({ ...capabilities, email_to: e.target.value })
                }
                placeholder="team@example.com"
              />
            </div>
          )}
        </div>
      </fieldset>
      <div className="mt-3">
        <AgentToolPicker selected={tools} onChange={onToolsChange} disabled={disabled} />
      </div>
      {mcpKit && (
        <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
          Last save pinned {mcpKit.tool_count ?? 0} tools, {mcpKit.prompt_count ?? 0} prompts,{" "}
          {mcpKit.resource_count ?? 0} resources
          {mcpKit.domain_slugs?.length ? ` for /${mcpKit.domain_slugs.join(" /")}` : ""}.
        </p>
      )}
    </details>
  );
}
