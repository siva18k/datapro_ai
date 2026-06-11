import { useState } from "react";
import { MarkdownChat } from "./MarkdownChat";
import { generateAskOutput, type ExportPayload } from "../utils/askExport";

const COLLAPSE_CHARS = 1_400;

type Props = {
  content: string;
  exportPayload?: ExportPayload;
  rowCount?: number;
};

export function ChatAssistantMessage({ content, exportPayload, rowCount }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [openingHtml, setOpeningHtml] = useState(false);

  const isLong = content.length > COLLAPSE_CHARS;
  const showFullHint = (rowCount ?? 0) > 10 || isLong;

  const openHtml = async () => {
    if (!exportPayload) return;
    setOpeningHtml(true);
    try {
      await generateAskOutput("html", exportPayload);
    } finally {
      setOpeningHtml(false);
    }
  };

  return (
    <div className="chat-assistant">
      <div
        className={`prose-chat${isLong && !expanded ? " prose-chat--clamped" : ""}`}
      >
        <MarkdownChat>{content}</MarkdownChat>
      </div>

      {isLong && (
        <button
          type="button"
          className="chat-view-more"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "View less" : "View more"}
        </button>
      )}

      {showFullHint && exportPayload && (
        <p className="chat-export-hint">
          {rowCount != null && rowCount > 10 && (
            <span>{rowCount} rows total — </span>
          )}
          <button
            type="button"
            className="chat-export-link"
            disabled={openingHtml}
            onClick={() => void openHtml()}
          >
            {openingHtml ? "Opening…" : "Open full report (HTML)"}
          </button>
        </p>
      )}
    </div>
  );
}
