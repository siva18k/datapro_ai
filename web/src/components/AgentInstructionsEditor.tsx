import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onFormat: () => void;
  formatting?: boolean;
  disabled?: boolean;
};

type MenuPos = { top: number; left: number };

export function AgentInstructionsEditor({
  value,
  onChange,
  onFormat,
  formatting = false,
  disabled = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const caretMarkerRef = useRef<HTMLSpanElement>(null);
  const menuItemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuFilter, setMenuFilter] = useState("");
  const [slashStart, setSlashStart] = useState<number | null>(null);
  const [caretIndex, setCaretIndex] = useState(0);
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null);
  const [menuHighlightIndex, setMenuHighlightIndex] = useState(0);

  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: api.listDomains,
  });

  const filteredDomains = useMemo(() => {
    if (!domains) return [];
    const q = menuFilter.toLowerCase();
    return domains.filter(
      (d) =>
        !q ||
        d.slug.toLowerCase().includes(q) ||
        d.name.toLowerCase().includes(q),
    );
  }, [domains, menuFilter]);

  const visibleDomains = useMemo(() => filteredDomains.slice(0, 8), [filteredDomains]);

  const syncMenuPosition = useCallback(() => {
    const marker = caretMarkerRef.current;
    const container = containerRef.current;
    const textarea = textareaRef.current;
    if (!marker || !container || !textarea || !menuOpen) return;
    const markerRect = marker.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const maxLeft = Math.max(0, textarea.clientWidth - 200);
    setMenuPos({
      top: markerRect.bottom - containerRect.top + 4,
      left: Math.min(Math.max(0, markerRect.left - containerRect.left), maxLeft),
    });
  }, [menuOpen]);

  const detectSlashMenu = useCallback((text: string, pos: number) => {
    const textBefore = text.slice(0, pos);
    const slashMatch = textBefore.match(/(?<![a-zA-Z0-9:/])\/([a-z0-9_-]*)$/i);
    if (slashMatch) {
      setMenuOpen(true);
      setMenuFilter((slashMatch[1] || "").toLowerCase());
      setSlashStart(pos - (slashMatch[1]?.length ?? 0) - 1);
    } else {
      setMenuOpen(false);
      setSlashStart(null);
      setMenuPos(null);
    }
  }, []);

  const insertDomain = (slug: string) => {
    const el = textareaRef.current;
    if (!el || slashStart === null) return;
    const before = value.slice(0, slashStart);
    const after = value.slice(el.selectionStart);
    const token = `/${slug}`;
    const trimmedAfter = after.replace(/^[a-z0-9_-]*/i, "");
    const spacer = trimmedAfter.startsWith(" ") || trimmedAfter.startsWith("\n") ? "" : " ";
    const next = `${before}${token}${spacer}${trimmedAfter}`;
    onChange(next);
    setMenuOpen(false);
    setSlashStart(null);
    setMenuFilter("");
    setMenuPos(null);
    setMenuHighlightIndex(0);
    requestAnimationFrame(() => {
      const pos = before.length + token.length + spacer.length;
      el.focus();
      el.setSelectionRange(pos, pos);
      setCaretIndex(pos);
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen && visibleDomains.length > 0) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setSlashStart(null);
        setMenuPos(null);
        setMenuHighlightIndex(0);
        e.preventDefault();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.min(i + 1, visibleDomains.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMenuHighlightIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertDomain(visibleDomains[menuHighlightIndex].slug);
        return;
      }
    }
    if (menuOpen && e.key === "Escape") {
      setMenuOpen(false);
      setSlashStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
      e.preventDefault();
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    const pos = e.target.selectionStart;
    onChange(next);
    setCaretIndex(pos);
    detectSlashMenu(next, pos);
  };

  const onSelect = () => {
    const el = textareaRef.current;
    if (!el) return;
    setCaretIndex(el.selectionStart);
    detectSlashMenu(value, el.selectionStart);
  };

  useLayoutEffect(() => {
    if (!menuOpen) return;
    const mirror = mirrorRef.current;
    const textarea = textareaRef.current;
    if (mirror && textarea) {
      mirror.scrollTop = textarea.scrollTop;
    }
    syncMenuPosition();
  }, [menuOpen, menuFilter, caretIndex, value, syncMenuPosition]);

  useEffect(() => {
    if (!menuOpen) return;
    if (menuHighlightIndex >= visibleDomains.length) {
      setMenuHighlightIndex(Math.max(0, visibleDomains.length - 1));
    }
  }, [visibleDomains.length, menuHighlightIndex, menuOpen]);

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
      setSlashStart(null);
      setMenuPos(null);
      setMenuHighlightIndex(0);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const mirrorText = value.slice(0, caretIndex);

  return (
    <div className="agent-instructions-editor field mb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="label mb-0">Instructions</label>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onFormat}
          disabled={disabled || formatting || !value.trim()}
        >
          {formatting ? "Formatting…" : "AI Format"}
        </button>
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        Type <code>/</code> to pin a domain. Write the goal in plain language — tools are chosen automatically.
      </p>
      <div ref={containerRef} className="agent-instructions-input relative mt-2">
        <div ref={mirrorRef} className="agent-instructions-mirror" aria-hidden>
          {mirrorText}
          <span ref={caretMarkerRef} className="agent-instructions-caret">
            |
          </span>
        </div>
        <textarea
          ref={textareaRef}
          className="textarea agent-instructions-textarea"
          value={value}
          onChange={onInput}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onScroll={syncMenuPosition}
          disabled={disabled}
          placeholder={"## Goal\nMonitor /finance revenue KPI…\n\n## Steps\n1. Query weekly revenue…"}
        />
        {menuOpen && visibleDomains.length > 0 && menuPos && (
          <div
            className="agent-slash-menu"
            role="listbox"
            style={{ top: menuPos.top, left: menuPos.left }}
            onMouseDown={(e) => e.preventDefault()}
          >
            {visibleDomains.map((d, index) => (
              <button
                key={d.id}
                ref={(el) => {
                  menuItemRefs.current[index] = el;
                }}
                type="button"
                className={`agent-slash-menu-item${index === menuHighlightIndex ? " agent-slash-menu-item--active" : ""}`}
                role="option"
                aria-selected={index === menuHighlightIndex}
                onMouseEnter={() => setMenuHighlightIndex(index)}
                onClick={() => insertDomain(d.slug)}
              >
                <span className="font-medium">/{d.slug}</span>
                <span className="text-zinc-500">{d.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {domains && domains.length > 0 && (
        <div className="agent-available-domains mt-2">
          <p className="mb-1.5 text-xs font-medium text-zinc-500">Available domains</p>
          <div className="flex flex-wrap gap-1.5">
            {domains.map((d) => (
              <span key={d.id} className="agent-domain-ref-chip">
                <span>{d.name}</span>
                <code className="agent-domain-ref-slug">/{d.slug}</code>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
