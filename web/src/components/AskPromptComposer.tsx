import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { Agent, AgentFlow } from "../types";
import { computeMentionMenuPos, type MentionMenuPos } from "../utils/mentionMenuPosition";
import { DomainScopePromptOptions } from "./DomainScopePromptOptions";
import { IconDebug } from "./SidebarNavIcons";

const TEXT_EXTENSIONS = /\.(txt|md|csv|json|xml|html|htm|log|yaml|yml)$/i;
const MAX_ATTACHMENT_BYTES = 512_000;

export interface AskAttachment {
  name: string;
  text: string;
}

type MenuPos = MentionMenuPos;

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
  selectedAgent: Agent | null;
  onSelectedAgentChange: (agent: Agent | null) => void;
  selectedFlow: AgentFlow | null;
  onSelectedFlowChange: (flow: AgentFlow | null) => void;
  showDebugToggle?: boolean;
  showAgentFlowSelection?: boolean;
  showDomainPillsInToolbar?: boolean;
  submitOnEnter?: boolean;
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
  selectedAgent,
  onSelectedAgentChange,
  selectedFlow,
  onSelectedFlowChange,
  showDebugToggle = true,
  showAgentFlowSelection = true,
  showDomainPillsInToolbar = false,
  submitOnEnter = true,
}: AskPromptComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const atMarkerRef = useRef<HTMLSpanElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuItemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const wasPendingRef = useRef(false);
  const [isFocused, setIsFocused] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuKind, setMenuKind] = useState<"agent" | "flow" | null>(null);
  const [menuFilter, setMenuFilter] = useState("");
  const [atStart, setAtStart] = useState<number | null>(null);
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null);
  const [menuHighlightIndex, setMenuHighlightIndex] = useState(0);

  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
  });

  const { data: flows } = useQuery({
    queryKey: ["agent-flows"],
    queryFn: api.listAgentFlows,
  });

  const enabledAgents = useMemo(
    () => (agents ?? []).filter((a) => a.enabled),
    [agents],
  );

  const enabledFlows = useMemo(
    () => (flows ?? []).filter((f) => f.enabled),
    [flows],
  );

  const filteredAgents = useMemo(() => {
    const q = menuFilter.toLowerCase();
    return enabledAgents.filter(
      (a) =>
        !q ||
        a.slug.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q),
    );
  }, [enabledAgents, menuFilter]);

  const filteredFlows = useMemo(() => {
    const q = menuFilter.toLowerCase();
    return enabledFlows.filter(
      (f) =>
        !q ||
        f.slug.toLowerCase().includes(q) ||
        f.name.toLowerCase().includes(q),
    );
  }, [enabledFlows, menuFilter]);

  const visibleAgents = useMemo(() => filteredAgents.slice(0, 8), [filteredAgents]);
  const visibleFlows = useMemo(() => filteredFlows.slice(0, 8), [filteredFlows]);
  const visibleMenuItems = menuKind === "flow" ? visibleFlows : visibleAgents;

  const canSend = Boolean((value.trim() || (showAgentFlowSelection && (selectedAgent || selectedFlow))) && !isPending);
  const hasContent = value.length > 0 || attachments.length > 0 || (showAgentFlowSelection && (Boolean(selectedAgent) || Boolean(selectedFlow)));
  const showFocusEffects = isFocused && hasContent;
  const textRows = Math.min(Math.max(value.split("\n").length, 1), 8);

  useEffect(() => {
    if (wasPendingRef.current && !isPending) {
      setSubmitted(true);
      textareaRef.current?.blur();
      setIsFocused(false);
    }
    wasPendingRef.current = isPending;
  }, [isPending]);

  const syncMenuPosition = useCallback(() => {
    const marker = atMarkerRef.current;
    if (!marker || !menuOpen || atStart === null) return;
    setMenuPos(computeMentionMenuPos(marker));
  }, [menuOpen, atStart]);

  const detectAtMenu = useCallback((text: string, pos: number) => {
    if (!showAgentFlowSelection) return;
    const textBefore = text.slice(0, pos);
    const flowMatch = textBefore.match(/(?:^|\s)@@([a-z0-9_-]*)$/i);
    if (flowMatch) {
      setMenuOpen(true);
      setMenuKind("flow");
      setMenuFilter((flowMatch[1] || "").toLowerCase());
      setAtStart(pos - (flowMatch[1]?.length ?? 0) - 2);
      setMenuHighlightIndex(0);
      return;
    }
    const atMatch = textBefore.match(/(?:^|\s)@(?!@)([a-z0-9_-]*)$/i);
    if (atMatch) {
      setMenuOpen(true);
      setMenuKind("agent");
      setMenuFilter((atMatch[1] || "").toLowerCase());
      setAtStart(pos - (atMatch[1]?.length ?? 0) - 1);
      setMenuHighlightIndex(0);
    } else {
      setMenuOpen(false);
      setMenuKind(null);
      setAtStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
    }
  }, [showAgentFlowSelection]);

  const insertAgent = (agent: Agent) => {
    const el = textareaRef.current;
    if (!el || atStart === null) return;
    const before = value.slice(0, atStart).replace(/\s$/, "");
    const after = value.slice(el.selectionStart).replace(/^[a-z0-9_-]*/i, "");
    const spacer = before.length > 0 && !before.endsWith("\n") ? " " : "";
    const next = `${before}${spacer}${after}`.replace(/^\s+/, "");
    onChange(next);
    onSelectedAgentChange(agent);
    onSelectedFlowChange(null);
    setMenuOpen(false);
    setMenuKind(null);
    setAtStart(null);
    setMenuFilter("");
    setMenuPos(null);
    setMenuHighlightIndex(0);
    requestAnimationFrame(() => {
      const pos = before.length + spacer.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  };

  const insertFlow = (flow: AgentFlow) => {
    const el = textareaRef.current;
    if (!el || atStart === null) return;
    const before = value.slice(0, atStart).replace(/\s$/, "");
    const after = value.slice(el.selectionStart).replace(/^[a-z0-9_-]*/i, "");
    const spacer = before.length > 0 && !before.endsWith("\n") ? " " : "";
    const next = `${before}${spacer}${after}`.replace(/^\s+/, "");
    onChange(next);
    onSelectedFlowChange(flow);
    onSelectedAgentChange(null);
    setMenuOpen(false);
    setMenuKind(null);
    setAtStart(null);
    setMenuFilter("");
    setMenuPos(null);
    setMenuHighlightIndex(0);
    requestAnimationFrame(() => {
      const pos = before.length + spacer.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  };

  const shellClass = [
    "ask-composer-shell",
    isPending ? "ask-composer-shell--pending" : "",
    !isPending && !submitted && hasContent ? "ask-composer-shell--engaged" : "",
    showFocusEffects ? "ask-composer-shell--focused" : "",
    !isPending && value.length > 0 ? "ask-composer-shell--typing" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen && visibleMenuItems.length > 0) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setMenuKind(null);
        setAtStart(null);
        setMenuPos(null);
        setMenuHighlightIndex(0);
        e.preventDefault();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.min(i + 1, visibleMenuItems.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (menuKind === "flow") {
          insertFlow(visibleFlows[menuHighlightIndex]);
        } else {
          insertAgent(visibleAgents[menuHighlightIndex]);
        }
        return;
      }
    }
    if (menuOpen) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setAtStart(null);
        setMenuPos(null);
        setMenuHighlightIndex(0);
        e.preventDefault();
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        return;
      }
    }
    if (submitOnEnter) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) onSubmit();
      }
    } else {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (canSend) onSubmit();
      }
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    const pos = e.target.selectionStart;
    if (submitted) setSubmitted(false);
    onChange(next);
    detectAtMenu(next, pos);
  };

  const onSelect = () => {
    const el = textareaRef.current;
    if (!el) return;
    detectAtMenu(value, el.selectionStart);
  };

  useLayoutEffect(() => {
    if (!menuOpen) return;
    const mirror = mirrorRef.current;
    const textarea = textareaRef.current;
    if (mirror && textarea) {
      mirror.scrollTop = textarea.scrollTop;
    }
    syncMenuPosition();
  }, [menuOpen, menuFilter, atStart, value, syncMenuPosition]);

  useEffect(() => {
    if (!menuOpen) return;
    if (menuHighlightIndex >= visibleMenuItems.length) {
      setMenuHighlightIndex(Math.max(0, visibleMenuItems.length - 1));
    }
  }, [visibleMenuItems.length, menuHighlightIndex, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    setMenuHighlightIndex(0);
  }, [menuFilter, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    menuItemRefs.current[menuHighlightIndex]?.scrollIntoView({ block: "nearest" });
  }, [menuHighlightIndex, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      const target = e.target as Node;
      if (containerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setMenuOpen(false);
      setAtStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const onViewportChange = () => syncMenuPosition();
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    return () => {
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [menuOpen, syncMenuPosition]);

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

  const atMirrorText = atStart !== null ? value.slice(0, atStart) : "";
  const atMirrorSuffix = menuKind === "flow" ? "@@" : "@";

  const mentionMenuPortal =
    menuOpen && menuPos
      ? createPortal(
          visibleMenuItems.length > 0 ? (
            <div
              id="ask-agent-menu"
              ref={menuRef}
              className={`agent-slash-menu ask-agent-menu ask-agent-menu-portal${menuPos.placement === "above" ? " ask-agent-menu--above" : ""}`}
              role="listbox"
              style={{ top: menuPos.top, left: menuPos.left }}
              onMouseDown={(e) => e.preventDefault()}
            >
              {menuKind === "flow"
                ? visibleFlows.map((f, index) => (
                    <button
                      key={f.id}
                      id={`ask-menu-option-flow-${index}`}
                      ref={(el) => {
                        menuItemRefs.current[index] = el;
                      }}
                      type="button"
                      className={`agent-slash-menu-item${index === menuHighlightIndex ? " agent-slash-menu-item--active" : ""}`}
                      role="option"
                      aria-selected={index === menuHighlightIndex}
                      onMouseEnter={() => setMenuHighlightIndex(index)}
                      onClick={() => insertFlow(f)}
                    >
                      <span className="font-medium">@@{f.slug}</span>
                      <span className="mention-menu-item-meta">{f.name}</span>
                    </button>
                  ))
                : visibleAgents.map((a, index) => (
                    <button
                      key={a.id}
                      id={`ask-menu-option-agent-${index}`}
                      ref={(el) => {
                        menuItemRefs.current[index] = el;
                      }}
                      type="button"
                      className={`agent-slash-menu-item${index === menuHighlightIndex ? " agent-slash-menu-item--active" : ""}`}
                      role="option"
                      aria-selected={index === menuHighlightIndex}
                      onMouseEnter={() => setMenuHighlightIndex(index)}
                      onClick={() => insertAgent(a)}
                    >
                      <span className="font-medium">@{a.slug}</span>
                      <span className="mention-menu-item-meta">{a.name}</span>
                    </button>
                  ))}
            </div>
          ) : (
            <div
              ref={menuRef}
              className={`agent-slash-menu ask-agent-menu ask-agent-menu-portal${menuPos.placement === "above" ? " ask-agent-menu--above" : ""}`}
              style={{ top: menuPos.top, left: menuPos.left }}
              onMouseDown={(e) => e.preventDefault()}
            >
              <p className="mention-menu-empty">
                {menuKind === "flow" ? "No flows match" : "No agents match"}
              </p>
            </div>
          ),
          document.body,
        )
      : null;

  return (
    <div className={`ask-composer-stack${menuOpen ? " ask-composer-stack--menu-open" : ""}`}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) onSubmit();
        }}
        className="ask-composer-form"
      >
        <div className={shellClass}>
          <div className={`ask-composer-inner${menuOpen ? " ask-composer-inner--menu-open" : ""}`}>
          {(showAgentFlowSelection && (selectedAgent || selectedFlow)) && (
            <div className="ask-composer-attachments">
              {showAgentFlowSelection && selectedFlow && (
                <span className="ask-composer-agent-chip ask-composer-flow-chip">
                  <span className="ask-composer-agent-chip-label">@@{selectedFlow.name}</span>
                  <button
                    type="button"
                    className="ask-composer-attachment-remove"
                    onClick={() => onSelectedFlowChange(null)}
                    disabled={isPending}
                    aria-label={`Remove flow ${selectedFlow.name}`}
                  >
                    ×
                  </button>
                </span>
              )}
              {showAgentFlowSelection && selectedAgent && (
                <span className="ask-composer-agent-chip">
                  <span className="ask-composer-agent-chip-label">@{selectedAgent.name}</span>
                  <button
                    type="button"
                    className="ask-composer-attachment-remove"
                    onClick={() => onSelectedAgentChange(null)}
                    disabled={isPending}
                    aria-label={`Remove agent ${selectedAgent.name}`}
                  >
                    ×
                  </button>
                </span>
              )}
            </div>
          )}

          <div ref={containerRef} className="ask-composer-input-wrap relative">
            <div ref={mirrorRef} className="ask-composer-mirror" aria-hidden>
              {atMirrorText}
              <span ref={atMarkerRef} className="ask-composer-at-marker">{atMirrorSuffix}</span>
            </div>
            <textarea
              ref={textareaRef}
              className="ask-composer-input"
              rows={submitOnEnter ? 1 : textRows}
              placeholder={
                showAgentFlowSelection && selectedFlow
                  ? "Add instructions for this flow run…"
                  : showAgentFlowSelection && selectedAgent
                    ? "Add instructions for this agent run…"
                    : showAgentFlowSelection
                      ? "Ask a question — @ for an agent, @@ for a flow — e.g. travel policy, revenue by region"
                      : "Ask a question — e.g. travel policy, revenue by region"
              }
              value={value}
              onChange={onInput}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onKeyDown={onKeyDown}
              onSelect={onSelect}
              onScroll={syncMenuPosition}
              disabled={isPending}
              aria-busy={isPending}
              aria-expanded={menuOpen}
              aria-autocomplete="list"
              aria-controls={menuOpen ? "ask-agent-menu" : undefined}
              aria-activedescendant={
                menuOpen && visibleMenuItems.length > 0
                  ? `ask-menu-option-${menuKind}-${menuHighlightIndex}`
                  : undefined
              }
            />
          </div>

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
              {attachments.length > 0 && (
                <div className="ask-composer-attachment-list">
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
              {showDomainPillsInToolbar && (
                <DomainScopePromptOptions
                  selectedSlugs={selectedDomains}
                  onChange={onSelectedDomainsChange}
                />
              )}
            </div>
            <button
              type="submit"
              className="ask-composer-send-btn"
              disabled={!canSend}
              aria-label={selectedFlow ? "Run flow" : selectedAgent ? "Run agent" : "Send question"}
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
        {!showDomainPillsInToolbar && (
          <DomainScopePromptOptions
            selectedSlugs={selectedDomains}
            onChange={onSelectedDomainsChange}
          />
        )}
        {showDebugToggle && (
          <OptionPill
            active={debugMode}
            onClick={() => onDebugModeChange(!debugMode)}
            icon={<IconDebug width={14} height={14} />}
            label="Debug"
          />
        )}
      </div>

      {error && <p className="alert-error mt-2 text-sm">{error}</p>}
      {mentionMenuPortal}
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
