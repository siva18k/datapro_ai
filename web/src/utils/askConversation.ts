export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

interface AskMessageLike {
  role: "user" | "assistant";
  content: string;
  agentRun?: unknown;
  flowRun?: unknown;
}

/** Build prior turns for follow-up Ask requests (excludes agent/flow runs). */
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
    turns.push({ role: message.role, content });
  }

  return turns.slice(-maxTurns * 2);
}
