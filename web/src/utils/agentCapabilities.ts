import type { AgentCapabilities } from "../types";

const KPI_RE = /\b(kpi|pass|fail|threshold|metric|rules?)\b/i;
const REPORT_RE = /\b(report|html|table|chart|dashboard|list|inventory|summary)\b/i;
const EMAIL_RE = /\b(e-?mail|notify|notification|smtp)\b/i;

export function inferAgentCapabilities(instructions: string): AgentCapabilities {
  const kpi = KPI_RE.test(instructions);
  const report = REPORT_RE.test(instructions);
  const email = EMAIL_RE.test(instructions);
  return {
    kpi_check: kpi || (!kpi && !report),
    generate_report: report || (!kpi && !report),
    send_email: email,
  };
}
