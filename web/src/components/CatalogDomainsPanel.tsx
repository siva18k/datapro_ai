import { useSidebarCollapsed } from "../context/SidebarContext";
import type { Domain } from "../types";
import { SidebarHint } from "./SidebarHint";
import { IconDomains } from "./SidebarNavIcons";

export function CatalogDomainsPanel({
  domains,
  loading,
  activeDomainId,
  onSelectDomain,
  showAddDomain,
  onShowAddDomain,
  newDomainName,
  onNewDomainNameChange,
  onCreateDomain,
  creating,
  onDeleteDomain,
  deletingDomainId,
}: {
  domains?: Domain[];
  loading: boolean;
  activeDomainId: string | null;
  onSelectDomain: (id: string) => void;
  showAddDomain: boolean;
  onShowAddDomain: (show: boolean) => void;
  newDomainName: string;
  onNewDomainNameChange: (value: string) => void;
  onCreateDomain: () => void;
  creating: boolean;
  onDeleteDomain?: (domain: Domain) => void;
  deletingDomainId?: string | null;
}) {
  const collapsed = useSidebarCollapsed();

  if (collapsed) {
    const active = domains?.find((d) => d.id === activeDomainId);
    return (
      <div className="sidebar-collapsed-stack">
        <SidebarHint hint={`Domains (${domains?.length ?? 0})`}>
          <IconDomains />
        </SidebarHint>
        {domains?.map((d) => (
          <SidebarHint
            key={d.id}
            hint={d.name}
            active={activeDomainId === d.id}
            onClick={() => onSelectDomain(d.id)}
          >
            <span className="sidebar-domain-initial">{d.name.charAt(0).toUpperCase()}</span>
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
      <p className="sidebar-panel-title">Domains</p>
      {loading && <p className="text-xs text-zinc-400">Loading…</p>}
      <div className="space-y-0.5">
        {domains?.map((d) => (
          <div key={d.id} className="sidebar-domain-row">
            <button
              type="button"
              onClick={() => onSelectDomain(d.id)}
              className={`sidebar-domain-btn ${activeDomainId === d.id ? "sidebar-domain-btn-active" : ""}`}
            >
              {d.name}
            </button>
            {onDeleteDomain && (
              <button
                type="button"
                className="sidebar-domain-delete icon-btn"
                aria-label={`Remove domain ${d.name}`}
                title="Remove domain"
                disabled={deletingDomainId === d.id}
                onClick={() => onDeleteDomain(d)}
              >
                {deletingDomainId === d.id ? "…" : "×"}
              </button>
            )}
          </div>
        ))}
      </div>
      {showAddDomain ? (
        <div className="mt-3 space-y-2 border-t border-zinc-200 pt-3">
          <input
            className="input"
            placeholder="Domain name"
            value={newDomainName}
            onChange={(e) => onNewDomainNameChange(e.target.value)}
          />
          <div className="flex gap-1">
            <button
              type="button"
              className="btn btn-sm flex-1"
              disabled={!newDomainName.trim() || creating}
              onClick={onCreateDomain}
            >
              Add
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => onShowAddDomain(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="btn-ghost btn-sm mt-3 w-full text-left" onClick={() => onShowAddDomain(true)}>
          + Domain
        </button>
      )}
    </div>
  );
}
