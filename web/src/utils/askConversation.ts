export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
  question?: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
}

interface AskMessageLike {
  role: "user" | "assistant";
  content: string;
  question?: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  agentRun?: unknown;
  flowRun?: unknown;
}

const BREAKDOWN_DIMENSIONS: Record<string, string[]> = {
  channel: ["channel", "channels"],
  country: ["country", "countries"],
  region: ["region", "regions"],
  quarter: ["quarter", "quarterly", " q1", " q2", " q3", " q4"],
  month: ["month", "monthly"],
  year: ["year", "yearly", "annual"],
  customer: ["customer", "customers"],
  product: ["product", "products"],
  category: ["category", "categories"],
  department: ["department", "departments"],
};

function breakdownDimensions(text: string): Set<string> {
  const lower = text.toLowerCase();
  const dims = new Set<string>();
  for (const [dim, tokens] of Object.entries(BREAKDOWN_DIMENSIONS)) {
    if (tokens.some((token) => lower.includes(token))) dims.add(dim);
  }
  return dims;
}

function lastUserMessage(messages: AskMessageLike[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role === "user") return messages[i].content?.trim() ?? "";
  }
  return "";
}

/** Skip prior turns when the new prompt is clearly a fresh question, not a refinement. */
export function shouldSendConversationHistory(
  messages: AskMessageLike[],
  nextPrompt: string,
): boolean {
  if (!messages.length) return false;
  const last = lastUserMessage(messages);
  const next = nextPrompt.trim();
  if (!last || !next) return false;
  if (last.toLowerCase() === next.toLowerCase()) return true;

  const q = next.toLowerCase();
  if (/^(also|and|same|filter|sort|order|convert|exclude|include|only|what about|how about|add|drop|remove|keep|limit)\b/.test(q)) {
    return true;
  }

  const curDims = breakdownDimensions(next);
  const prevDims = breakdownDimensions(last);
  if (curDims.size && prevDims.size && !setsEqual(curDims, prevDims)) return false;

  if (!/\b(that|those|same|previous|prior|above|earlier|it|them)\b/i.test(next)) {
    if (curDims.size !== prevDims.size) return false;
  }

  return true;
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false;
  for (const value of a) if (!b.has(value)) return false;
  return true;
}

/** Build prior turns for follow-up Ask / Analytics requests (excludes agent/flow runs). */
export function buildAskConversationHistory(
  messages: AskMessageLike[],
  maxTurns: number,
): ConversationTurn[] {
  if (maxTurns <= 0) return [];

  const turns: ConversationTurn[] = [];
  for (const message of messages) {
    if (message.agentRun || message.flowRun) continue;
    const content = message.content?.trim();
    if (!content) continue;
    const turn: ConversationTurn = { role: message.role, content };
    if (message.question) turn.question = message.question;
    if (message.sql) turn.sql = message.sql;
    if (message.columns?.length) turn.columns = message.columns;
    if (message.rows) turn.rows = message.rows;
    turns.push(turn);
  }

  return turns.slice(-maxTurns * 2);
}

/** Assistant message(s) shown when the backend resets the session. */
export function sessionResetTurns(res: {
  session_reset?: boolean;
  session_summary?: string | null;
  new_topic?: boolean;
}): ConversationTurn[] {
  if (!res.session_reset) return [];
  if (res.session_summary?.trim()) {
    return [
      {
        role: "assistant",
        content: `**Previous conversation summary**\n\n${res.session_summary.trim()}`,
      },
    ];
  }
  if (res.new_topic) {
    return [{ role: "assistant", content: "*New topic — prior context cleared.*" }];
  }
  return [];
}
