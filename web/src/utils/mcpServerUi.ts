import type { McpServerRecord } from "../api/client";

/** Theme-aware card tint by server type. */
export function mcpServerCardClass(server: McpServerRecord): string {
  const variant =
    server.is_builtin || server.slug === "datapro"
      ? "mcp-server-card--builtin"
      : server.slug === "email_smtp"
        ? "mcp-server-card--email"
        : server.server_kind === "enterprise"
          ? "mcp-server-card--enterprise"
          : "mcp-server-card--public";
  return `card card-pad mcp-server-card ${variant}`;
}

export function mcpServerTagline(server: McpServerRecord): string {
  switch (server.slug) {
    case "datapro":
      return "Built-in knowledge base MCP";
    case "email_smtp":
      return "Email via SMTP/IMAP";
    default:
      if (server.server_kind === "enterprise") return "Enterprise MCP endpoint";
      return "External MCP endpoint";
  }
}

/** Extra setup / usage notes shown only in the edit dialog. */
export function mcpServerSetupNotes(server: McpServerRecord): string | null {
  switch (server.slug) {
    case "datapro":
      return (
        "Runs search_documents, list_domains, ragpro:// resources, and grounded-answer prompts. " +
        "Restart after editing global prompts in the registry."
      );
    case "email_smtp":
      return (
        "Free email via Gmail app password or any SMTP/IMAP provider.\n\n" +
        "Before starting, set in .env (see .env.example):\n" +
        "• SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM\n" +
        "• IMAP_HOST, IMAP_USER, IMAP_PASSWORD (optional, for search_inbox)\n" +
        "• EMAIL_TO_ALLOWLIST (optional, restricts send recipients)\n\n" +
        "Start from this page or run: python email_mcp_server.py"
      );
    default:
      return server.description?.trim() || null;
  }
}
