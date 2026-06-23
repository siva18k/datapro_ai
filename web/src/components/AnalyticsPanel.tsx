import { DomainScopePicker } from "./DomainScopePicker";
import { useSidebarCollapsed } from "../context/SidebarContext";

export function AnalyticsPanel({
  selectedDomains,
  onSelectedDomainsChange,
}: {
  selectedDomains: string[];
  onSelectedDomainsChange: (value: string[]) => void;
}) {
  const collapsed = useSidebarCollapsed();

  if (collapsed) {
    return (
      <div className="sidebar-collapsed-stack">
        <DomainScopePicker
          selectedSlugs={selectedDomains}
          onChange={onSelectedDomainsChange}
          collapsedHintPrefix="Analytics scope"
        />
      </div>
    );
  }

  return (
    <div className="sidebar-panel sidebar-panel-compact">
      <p className="sidebar-panel-title">Analytics scope</p>
      <DomainScopePicker
        selectedSlugs={selectedDomains}
        onChange={onSelectedDomainsChange}
        title="Domains"
        collapsedHintPrefix="Analytics scope"
      />
    </div>
  );
}
