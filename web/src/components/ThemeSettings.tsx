import { useEffect, useRef, useState } from "react";
import { useTheme, type Theme } from "../context/ThemeContext";

const OPTIONS: { value: Theme; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

const COLLAPSED_ICON_SIZE = 18;

function ThemeIcon({
  size = 20,
  strokeWidth = 2,
}: {
  size?: number;
  strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      aria-hidden
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

export function ThemeSettings({
  placement = "below",
  compact = false,
}: {
  placement?: "above" | "below";
  compact?: boolean;
}) {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="theme-settings" ref={rootRef}>
      <button
        type="button"
        className={`icon-btn${compact ? " sidebar-footer-icon-btn" : ""}`}
        aria-label="Theme"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <ThemeIcon
          size={compact ? COLLAPSED_ICON_SIZE : 20}
          strokeWidth={compact ? 2.25 : 2}
        />
      </button>
      {open && (
        <div
          className={`theme-menu${
            compact ? " theme-menu--sidebar" : placement === "above" ? " theme-menu--above" : ""
          }`}
          role="menu"
        >
          <p className="theme-menu-title">Theme</p>
          {OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="menuitemradio"
              aria-checked={theme === opt.value}
              className={`theme-menu-item ${theme === opt.value ? "theme-menu-item-active" : ""}`}
              onClick={() => {
                setTheme(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
