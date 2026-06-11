import { api } from "../api/client";
import type { OutputFormat } from "../components/AskOutputOptions";

export interface ExportPayload {
  question: string;
  answer: string;
  domain_name?: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
}

function downloadText(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function openHtmlTab(content: string) {
  const blob = new Blob([content], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function generateAskOutput(format: OutputFormat, payload: ExportPayload) {
  const res = await api.askExport({ format, ...payload });
  if (format === "csv") {
    downloadText(res.content, res.filename, res.content_type);
    return;
  }
  openHtmlTab(res.content);
}
