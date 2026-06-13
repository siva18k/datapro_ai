import { useEffect, useRef, useState } from "react";
import { DomainScopePromptOptions } from "./DomainScopePromptOptions";
import { IconDebug } from "./SidebarNavIcons";

const TEXT_EXTENSIONS = /\.(txt|md|csv|json|xml|html|htm|log|yaml|yml)$/i;
const MAX_ATTACHMENT_BYTES = 512_000;

export interface AskAttachment {
  name: string;
  text: string;
}

interface AskPromptComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isPending: boolean;
  error?: string | null;
  attachments: AskAttachment[];
  onAttachmentsChange: (attachments: AskAttachment[]) => void;
  debugMode: boolean;
  onDebugModeChange: (value: boolean) => void;
  selectedDomains: string[];
  onSelectedDomainsChange: (slugs: string[]) => void;
}

function OptionPill({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`ask-composer-pill${active ? " ask-composer-pill--active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      <span className="ask-composer-pill-icon" aria-hidden>
        {icon}
      </span>
      {label}
    </button>
  );
}

export function AskPromptComposer({
  value,
  onChange,
  onSubmit,
  isPending,
  error,
  attachments,
  onAttachmentsChange,
  debugMode,
  onDebugModeChange,
  selectedDomains,
  onSelectedDomainsChange,
}: AskPromptComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const wasPendingRef = useRef(false);
  const [isFocused, setIsFocused] = useState(false);
  const canSend = Boolean(value.trim()) && !isPending;
  const hasContent = value.length > 0 || attachments.length > 0;
  const showFocusEffects = isFocused && hasContent;

  useEffect(() => {
    if (wasPendingRef.current && !isPending) {
      textareaRef.current?.blur();
      setIsFocused(false);
    }
    wasPendingRef.current = isPending;
  }, [isPending]);

  const shellClass = [
    "ask-composer-shell",
    isPending ? "ask-composer-shell--pending" : "",
    !isPending && hasContent ? "ask-composer-shell--engaged" : "",
    showFocusEffects ? "ask-composer-shell--focused" : "",
    !isPending && value.length > 0 ? "ask-composer-shell--typing" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  const onPickFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const next = [...attachments];
    for (const file of Array.from(files)) {
      if (file.size > MAX_ATTACHMENT_BYTES) continue;
      const isText = TEXT_EXTENSIONS.test(file.name) || file.type.startsWith("text/");
      if (!isText && file.type !== "application/json") continue;
      try {
        const text = await file.text();
        next.push({ name: file.name, text: text.slice(0, 12_000) });
      } catch {
        /* skip unreadable files */
      }
    }
    if (next.length !== attachments.length) onAttachmentsChange(next);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (index: number) => {
    onAttachmentsChange(attachments.filter((_, i) => i !== index));
  };

  return (
    <div className="ask-composer-stack">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) onSubmit();
        }}
        className="ask-composer-form"
      >
        <div className={shellClass}>
          <div className="ask-composer-inner">
          {attachments.length > 0 && (
            <div className="ask-composer-attachments">
              {attachments.map((file, i) => (
                <span key={`${file.name}-${i}`} className="ask-composer-attachment">
                  <span className="ask-composer-attachment-name">{file.name}</span>
                  <button
                    type="button"
                    className="ask-composer-attachment-remove"
                    onClick={() => removeAttachment(i)}
                    aria-label={`Remove ${file.name}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          <textarea
            ref={textareaRef}
            className="ask-composer-input"
            rows={1}
            placeholder="Ask a question… e.g. travel policy, revenue by region"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onKeyDown={onKeyDown}
            disabled={isPending}
            aria-busy={isPending}
          />

          <div className="ask-composer-toolbar">
            <div className="ask-composer-toolbar-left">
              <input
                ref={fileInputRef}
                type="file"
                className="ask-composer-file-input"
                accept=".txt,.md,.csv,.json,.xml,.html,.htm,.log,.yaml,.yml,text/*,application/json"
                multiple
                onChange={(e) => void onPickFiles(e.target.files)}
              />
              <button
                type="button"
                className="ask-composer-add-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={isPending}
                aria-label="Add document"
                title="Attach a text document"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            </div>
            <button
              type="submit"
              className="ask-composer-send-btn"
              disabled={!canSend}
              aria-label="Send question"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          </div>
          </div>
        </div>
      </form>

      <div className="ask-composer-options">
        <DomainScopePromptOptions
          selectedSlugs={selectedDomains}
          onChange={onSelectedDomainsChange}
        />
        <OptionPill
          active={debugMode}
          onClick={() => onDebugModeChange(!debugMode)}
          icon={<IconDebug width={14} height={14} />}
          label="Debug"
        />
      </div>

      {error && <p className="alert-error mt-2 text-sm">{error}</p>}
    </div>
  );
}

export function buildAskQuestion(question: string, attachments: AskAttachment[]): string {
  const q = question.trim();
  if (!attachments.length) return q;
  const docs = attachments
    .map((file) => `--- ${file.name} ---\n${file.text}`)
    .join("\n\n");
  return `${q}\n\n[Attached documents]\n${docs}`;
}
