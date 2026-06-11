import { NavLink, Outlet } from "react-router-dom";
import { ApiOfflineBanner } from "./ApiOfflineBanner";
import { AppBrand } from "./AppBrand";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  useSidebarCollapsed,
  useSidebarContent,
  useSidebarToggle,
} from "../context/SidebarContext";
import { SidebarFooter } from "./SidebarFooter";
import { ThemeSettings } from "./ThemeSettings";
import { useResizableSidebar } from "../hooks/useResizableSidebar";
import {
  IconAnalytics,
  IconAsk,
  IconCatalog,
  IconCollapse,
  IconExpand,
  IconMcp,
  IconRag,
} from "./SidebarNavIcons";
import type { ComponentType, SVGProps } from "react";

type NavItemConfig = {
  to: string;
  label: string;
  end?: boolean;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
};

const mainNav: NavItemConfig[] = [
  { to: "/ask", label: "Ask", Icon: IconAsk },
  { to: "/analytics", label: "Analytics", Icon: IconAnalytics },
];

const bottomNav: NavItemConfig[] = [
  { to: "/rag", label: "RAG", Icon: IconRag },
  { to: "/mcp", label: "MCP", Icon: IconMcp },
  { to: "/", label: "Data Catalog", end: true, Icon: IconCatalog },
];

function NavItem({
  to,
  label,
  end,
  Icon,
  collapsed,
}: {
  to: string;
  label: string;
  end?: boolean;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) =>
        `nav-link${collapsed ? " nav-link--collapsed" : ""} ${isActive ? "nav-link-active" : ""}`
      }
    >
      {collapsed ? <Icon /> : label}
    </NavLink>
  );
}

export function Layout() {
  const sidebarContent = useSidebarContent();
  const collapsed = useSidebarCollapsed();
  const { toggleCollapsed } = useSidebarToggle();
  const { width, onResizeStart } = useResizableSidebar();
  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : width;

  return (
    <div className="flex min-h-screen">
      <aside
        className={`sidebar hidden md:flex${collapsed ? " sidebar--collapsed" : ""}`}
        style={{ width: sidebarWidth }}
      >
        <div
          className={`sidebar-brand border-b${collapsed ? " sidebar-brand--collapsed" : ""}`}
          style={{ borderColor: "var(--color-border-light)" }}
        >
          {collapsed ? (
            <span className="sidebar-brand-mark" aria-label="DATA Pro">
              DP
            </span>
          ) : (
            <>
              <AppBrand size="lg" />
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                Multi-domain analytics
              </p>
            </>
          )}
          <button
            type="button"
            className="sidebar-collapse-btn icon-btn"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <IconExpand /> : <IconCollapse />}
          </button>
        </div>
        <nav className={`flex min-h-0 flex-1 flex-col${collapsed ? " sidebar-nav--collapsed" : " p-3"}`}>
          <div
            className={`shrink-0 space-y-0.5 border-b${collapsed ? " sidebar-nav-section--collapsed" : " pb-3"}`}
            style={{ borderColor: "var(--color-border-light)" }}
          >
            {mainNav.map((item) => (
              <NavItem key={item.to} {...item} collapsed={collapsed} />
            ))}
          </div>

          <div
            className={`min-h-0 flex-1 overflow-y-auto${collapsed ? " sidebar-page-hints" : " py-3"}`}
          >
            {sidebarContent}
          </div>

          <div
            className={`shrink-0 space-y-0.5 border-t${collapsed ? " sidebar-nav-section--collapsed" : " pt-3"}`}
            style={{ borderColor: "var(--color-border-light)" }}
          >
            {bottomNav.map((item) => (
              <NavItem key={item.to} {...item} collapsed={collapsed} />
            ))}
          </div>
        </nav>
        <SidebarFooter collapsed={collapsed} />

        {!collapsed && (
          <button
            type="button"
            className="sidebar-resize-handle"
            aria-label="Resize sidebar"
            onMouseDown={onResizeStart}
          />
        )}
      </aside>

      <main className="main" style={{ ["--sidebar-width" as string]: `${sidebarWidth}px` }}>
        <header
          className="border-b px-4 py-3 md:hidden"
          style={{ borderColor: "var(--color-border)", background: "var(--color-surface)" }}
        >
          <div className="flex items-center justify-between gap-3">
            <AppBrand size="sm" />
            <div className="flex items-center gap-1">
              <NavLink to="/settings" className="icon-btn" aria-label="Settings" title="Settings">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7z" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </NavLink>
              <ThemeSettings placement="below" />
            </div>
          </div>
          <nav className="mt-2 flex gap-3 text-sm">
            {[...mainNav, ...bottomNav].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive ? "mobile-nav-link-active font-medium" : "mobile-nav-link"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <div className="page-content">
          <ApiOfflineBanner />
          <Outlet />
        </div>
      </main>
    </div>
  );
}
