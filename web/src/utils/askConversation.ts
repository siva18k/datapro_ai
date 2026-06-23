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
