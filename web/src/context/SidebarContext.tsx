import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

const COLLAPSED_STORAGE_KEY = "datapro-sidebar-collapsed";
const LEGACY_COLLAPSED_STORAGE_KEY = "ragpro-sidebar-collapsed";
export const SIDEBAR_COLLAPSED_WIDTH = 60;

function readCollapsed(): boolean {
  try {
    return (
      localStorage.getItem(COLLAPSED_STORAGE_KEY) ??
      localStorage.getItem(LEGACY_COLLAPSED_STORAGE_KEY)
    ) === "true";
  } catch {
    return false;
  }
}

const SidebarContext = createContext<{
  setContent: (content: ReactNode | null) => void;
  collapsed: boolean;
  toggleCollapsed: () => void;
} | null>(null);

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode | null>(null);
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSED_STORAGE_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <SidebarContext.Provider value={{ setContent, collapsed, toggleCollapsed }}>
      <SidebarProviderInner content={content}>{children}</SidebarProviderInner>
    </SidebarContext.Provider>
  );
}

const SidebarContentContext = createContext<ReactNode | null>(null);

function SidebarProviderInner({ content, children }: { content: ReactNode | null; children: ReactNode }) {
  return (
    <SidebarContentContext.Provider value={content}>{children}</SidebarContentContext.Provider>
  );
}

export function useSidebarContent() {
  return useContext(SidebarContentContext);
}

export function useSidebarCollapsed() {
  return useContext(SidebarContext)?.collapsed ?? false;
}

export function useSidebarToggle() {
  const ctx = useContext(SidebarContext);
  return {
    collapsed: ctx?.collapsed ?? false,
    toggleCollapsed: ctx?.toggleCollapsed ?? (() => {}),
  };
}

/** Register page-specific content in the left sidebar (cleared on unmount). */
export function useSetSidebarContent(content: ReactNode | null) {
  const ctx = useContext(SidebarContext);
  useEffect(() => {
    if (!ctx) return;
    ctx.setContent(content);
    return () => ctx.setContent(null);
  }, [content, ctx]);
}
