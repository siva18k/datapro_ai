import { useSidebarCollapsed } from "../context/SidebarContext";
import { SidebarHint } from "./SidebarHint";

export type AgentsSidebarItem = {
  id: string;
  name: string;
  enabled: boolean;
};

export function AgentsSidebarPanel({
  title,
  items,
  loading,
  selectedId,
  onSelect,
  onCreate,
  creating,
  createLabel,
}: {
  title: string;
  items?: AgentsSidebarItem[];
  loading: boolean;
  selectedId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating: boolean;
  createLabel: string;
}) {
  const collapsed = useSidebarCollapsed();
  const active = items?.find((item) => item.id === selectedId);

  if (collapsed) {
    return (
      <div className="sidebar-collapsed-stack">
        <SidebarHint hint={title}>
          <span className="sidebar-domain-initial">{title.charAt(0)}</span>
        </SidebarHint>
        {items?.map((item) => (
          <SidebarHint
            key={item.id}
            hint={item.name}
            active={selectedId === item.id}
            onClick={() => onSelect(item.id)}
          >
            <span className="sidebar-domain-initial">{item.name.charAt(0).toUpperCase()}</span>
          </SidebarHint>
        ))}
        {active && (
          <span className="sidebar-collapsed-caption" title={`Active: ${active.name}`}>
            {active.name.slice(0, 3)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="sidebar-panel">
      <p className="sidebar-panel-title">{title}</p>
      {loading && (
        <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
          Loading…
        </p>
      )}
      <div className="space-y-0.5">
        {items?.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            className={`agents-list-tab${selectedId === item.id ? " agents-list-tab--active" : ""}`}
          >
            <span className="agents-list-tab-name">{item.name}</span>
            <span
              className={`agents-list-tab-dot${item.enabled ? " agents-list-tab-dot--on" : ""}`}
              title={item.enabled ? "Enabled" : "Disabled"}
              aria-label={item.enabled ? "Enabled" : "Disabled"}
            />
          </button>
        ))}
      </div>
      {!loading && !items?.length && (
        <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
          None yet. Create one to get started.
        </p>
      )}
      <button
        type="button"
        className="btn-ghost btn-sm mt-3 w-full text-left"
        disabled={creating}
        onClick={onCreate}
      >
        {creating ? "Creating…" : createLabel}
      </button>
    </div>
  );
}

/** Horizontal selector for narrow viewports when the app sidebar is hidden. */
export function AgentsTopSelector({
  title,
  items,
  loading,
  selectedId,
  onSelect,
  onCreate,
  creating,
  createLabel,
}: {
  title: string;
  items?: AgentsSidebarItem[];
  loading: boolean;
  selectedId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  creating: boolean;
  createLabel: string;
}) {
  return (
    <div className="agents-top-selector card card-pad">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>
          {title}
        </p>
        <button type="button" className="btn btn-secondary btn-sm" disabled={creating} onClick={onCreate}>
          {creating ? "Creating…" : createLabel}
        </button>
      </div>
      {loading && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Loading…
        </p>
      )}
      {!loading && items && items.length > 0 && (
        <div className="agents-top-selector-scroll">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`agents-top-selector-tab${selectedId === item.id ? " agents-top-selector-tab--active" : ""}`}
              onClick={() => onSelect(item.id)}
            >
              <span className="truncate">{item.name}</span>
              <span
                className={`agents-list-tab-dot${item.enabled ? " agents-list-tab-dot--on" : ""}`}
                aria-hidden
              />
            </button>
          ))}
        </div>
      )}
      {!loading && !items?.length && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          None yet. Create one to get started.
        </p>
      )}
    </div>
  );
}
