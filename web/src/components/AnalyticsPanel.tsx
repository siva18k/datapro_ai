import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSidebarCollapsed } from "../context/SidebarContext";
import { SidebarHint } from "./SidebarHint";
import { IconGlobe } from "./SidebarNavIcons";

export function AnalyticsPanel({
  domainOverride,
  onDomainOverrideChange,
}: {
  domainOverride: string;
  onDomainOverrideChange: (value: string) => void;
}) {
  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.listDomains(),
  });

  const collapsed = useSidebarCollapsed();
  const domainLabel =
    domainOverride
      ? domains?.find((d) => d.slug === domainOverride)?.name ?? domainOverride
      : "Auto-detect";

  if (collapsed) {
    return (
      <div className="sidebar-collapsed-stack">
        <SidebarHint hint={`Analytics scope · ${domainLabel}`}>
          <IconGlobe />
        </SidebarHint>
      </div>
    );
  }

  return (
    <div className="sidebar-panel sidebar-panel-compact">
      <p className="sidebar-panel-title">Analytics scope</p>
      <div className="sidebar-field mb-0">
        <label className="sidebar-label">Domain</label>
        <select className="select" value={domainOverride} onChange={(e) => onDomainOverrideChange(e.target.value)}>
          <option value="">Auto-detect</option>
          {domains?.map((d) => (
            <option key={d.id} value={d.slug}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
        Postgres datasets · auto-detect domain
      </p>
    </div>
  );
}
