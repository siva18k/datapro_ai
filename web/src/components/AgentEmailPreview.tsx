type Props = {
  to: string;
  subject: string;
  htmlBody: string;
  smtpConfigured: boolean;
  sent?: boolean;
};

export function AgentEmailPreview({ to, subject, htmlBody, smtpConfigured, sent = false }: Props) {
  const snippet = htmlBody.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 280);

  return (
    <div className="agent-email-preview card card-pad">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Email preview</h4>
        <span className={`text-xs ${smtpConfigured ? "text-amber-700" : "text-zinc-500"}`}>
          {sent ? "Sent" : smtpConfigured ? "Not sent (display only in v1)" : "Email MCP not configured"}
        </span>
      </div>
      <dl className="space-y-1 text-sm">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-zinc-500">To</dt>
          <dd className="min-w-0 break-all">{to || "—"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-zinc-500">Subject</dt>
          <dd className="min-w-0 break-all">{subject}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-zinc-600">{snippet}{snippet.length >= 280 ? "…" : ""}</p>
      {!smtpConfigured && (
        <p className="mt-2 text-xs text-zinc-500">
          Configure SMTP in <code>.env</code> and start the Email MCP to enable sending.
        </p>
      )}
    </div>
  );
}
