import { NavLink } from "react-router-dom";
import { ThemeSettings } from "./ThemeSettings";

function GearIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7z" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

export function SidebarFooter({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div
      className={`sidebar-footer flex items-center border-t ${
        collapsed ? "sidebar-footer--collapsed" : "justify-between gap-2 px-4 py-3"
      }`}
      style={{ borderColor: "var(--color-border-light)", color: "var(--color-text-faint)" }}
    >
      {!collapsed && (
        <a
          href="/about"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs hover:opacity-80 transition-opacity"
          style={{ color: "var(--color-text-faint)" }}
          title="About DATA Pro — how it works"
        >
          About
        </a>
      )}
      {collapsed && (
        <a
          href="/about"
          target="_blank"
          rel="noopener noreferrer"
          className="icon-btn"
          aria-label="About DATA Pro"
          title="About DATA Pro"
          style={{ fontSize: 14 }}
        >
          ?
        </a>
      )}
      <div className={`sidebar-footer-actions flex items-center ${collapsed ? "" : "gap-1"}`}>
        <NavLink
          to="/settings"
          className={({ isActive }) => `icon-btn ${isActive ? "icon-btn-active" : ""}`}
          aria-label="Settings"
          title="Settings"
        >
          <GearIcon />
        </NavLink>
        <ThemeSettings placement="above" />
      </div>
    </div>
  );
}
