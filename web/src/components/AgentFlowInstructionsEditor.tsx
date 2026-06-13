import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Agent } from "../types";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onAgentMentioned?: (agent: Agent) => void;
  disabled?: boolean;
};

type MenuPos = { top: number; left: number };

const DEFAULT_PLACEHOLDER =
  "Describe how agents interact. Type @ to mention agents — e.g. Run @kpi-checker first, pass KPI summary to @report-writer…";

export function AgentFlowInstructionsEditor({
  value,
  onChange,
  onAgentMentioned,
  disabled = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const atMarkerRef = useRef<HTMLSpanElement>(null);
  const menuItemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuFilter, setMenuFilter] = useState("");
  const [atStart, setAtStart] = useState<number | null>(null);
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null);
  const [menuHighlightIndex, setMenuHighlightIndex] = useState(0);

  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
  });

  const enabledAgents = useMemo(
    () => (agents ?? []).filter((a) => a.enabled),
    [agents],
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

  const visibleAgents = useMemo(() => filteredAgents.slice(0, 8), [filteredAgents]);

  const syncMenuPosition = useCallback(() => {
    const marker = atMarkerRef.current;
    const container = containerRef.current;
    if (!marker || !container || !menuOpen || atStart === null) return;
    const markerRect = marker.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const maxLeft = Math.max(0, container.clientWidth - 220);
    setMenuPos({
      top: markerRect.bottom - containerRect.top + 2,
      left: Math.min(Math.max(0, markerRect.left - containerRect.left), maxLeft),
    });
  }, [menuOpen, atStart]);

  const detectAtMenu = useCallback((text: string, pos: number) => {
    const textBefore = text.slice(0, pos);
    const atMatch = textBefore.match(/(?:^|\s)@(?!@)([a-z0-9_-]*)$/i);
    if (atMatch) {
      setMenuOpen(true);
      setMenuFilter((atMatch[1] || "").toLowerCase());
      setAtStart(pos - (atMatch[1]?.length ?? 0) - 1);
      setMenuHighlightIndex(0);
    } else {
      setMenuOpen(false);
      setAtStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
    }
  }, []);

  const insertAgent = (agent: Agent) => {
    const el = textareaRef.current;
    if (!el || atStart === null) return;
    const token = `@${agent.slug}`;
    const before = value.slice(0, atStart);
    const after = value.slice(el.selectionStart).replace(/^[a-z0-9_-]*/i, "");
    const next = `${before}${token}${after}`;
    onChange(next);
    onAgentMentioned?.(agent);
    setMenuOpen(false);
    setAtStart(null);
    setMenuFilter("");
    setMenuPos(null);
    setMenuHighlightIndex(0);
    requestAnimationFrame(() => {
      const pos = before.length + token.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen && visibleAgents.length > 0) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setAtStart(null);
        setMenuPos(null);
        setMenuHighlightIndex(0);
        e.preventDefault();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.min(i + 1, visibleAgents.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertAgent(visibleAgents[menuHighlightIndex]);
        return;
      }
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    const pos = e.target.selectionStart;
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
    if (menuHighlightIndex >= visibleAgents.length) {
      setMenuHighlightIndex(Math.max(0, visibleAgents.length - 1));
    }
  }, [visibleAgents.length, menuHighlightIndex, menuOpen]);

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
      if (containerRef.current?.contains(e.target as Node)) return;
      setMenuOpen(false);
      setAtStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const atMirrorText = atStart !== null ? value.slice(0, atStart) : "";

  return (
    <div className="agent-flow-instructions">
      <label className="mb-1 block text-xs font-medium text-zinc-500">
        Flow instructions
        <span className="ml-1 font-normal">— type @ to reference agents and describe data handoff</span>
      </label>
      <div
        ref={containerRef}
        className={`agent-instructions-input relative${menuOpen ? " agent-instructions-input--menu-open" : ""}`}
      >
        <div ref={mirrorRef} className="agent-instructions-mirror" aria-hidden>
          {atMirrorText}
          <span ref={atMarkerRef} className="agent-instructions-caret">@</span>
        </div>
        <textarea
          ref={textareaRef}
          className="input agent-instructions-textarea min-h-[5rem] w-full resize-y"
          rows={4}
          placeholder={DEFAULT_PLACEHOLDER}
          value={value}
          onChange={onInput}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onScroll={syncMenuPosition}
          disabled={disabled}
        />
        {menuOpen && visibleAgents.length > 0 && menuPos && (
          <div
            className="agent-slash-menu"
            role="listbox"
            style={{ top: menuPos.top, left: menuPos.left }}
            onMouseDown={(e) => e.preventDefault()}
          >
            {visibleAgents.map((a, index) => (
              <button
                key={a.id}
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
                <span className="text-zinc-500">{a.name}</span>
              </button>
            ))}
          </div>
        )}
        {menuOpen && filteredAgents.length === 0 && menuPos && (
          <div
            className="agent-slash-menu"
            style={{ top: menuPos.top, left: menuPos.left }}
            onMouseDown={(e) => e.preventDefault()}
          >
            <p className="px-3 py-2 text-xs text-zinc-500">No agents match</p>
          </div>
        )}
      </div>
    </div>
  );
}
