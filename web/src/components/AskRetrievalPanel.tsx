import { AskOutputOptions, type OutputFormat } from "./AskOutputOptions";
import { DomainScopePicker } from "./DomainScopePicker";
import { SidebarHint } from "./SidebarHint";
import { IconDebug, IconGlobe } from "./SidebarNavIcons";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSidebarCollapsed } from "../context/SidebarContext";
import { domainScopeLabel } from "./DomainScopeChips";

export function AskRetrievalPanel({
  selectedDomains,
  onSelectedDomainsChange,
  outputFormats,
  onOutputFormatsChange,
  debugMode,
}: {
  selectedDomains: string[];
  onSelectedDomainsChange: (value: string[]) => void;
  outputFormats: OutputFormat[];
  onOutputFormatsChange: (value: OutputFormat[]) => void;
  debugMode?: boolean;
}) {
  const collapsed = useSidebarCollapsed();
  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.listDomains(),
  });

  const domainLabel = domainScopeLabel(selectedDomains, domains);

  if (collapsed) {
    return (
      <div className="sidebar-collapsed-stack">
        <SidebarHint hint={`Domain: ${domainLabel}`}>
          <IconGlobe />
        </SidebarHint>
        {debugMode && (
          <SidebarHint hint="Debug mode on">
            <IconDebug />
          </SidebarHint>
        )}
        <AskOutputOptions
          selected={outputFormats}
          onChange={onOutputFormatsChange}
          collapsed
        />
      </div>
    );
  }

  return (
    <>
      <div className="sidebar-panel sidebar-panel-compact">
        <p className="sidebar-panel-title">Retrieval</p>
        <DomainScopePicker
          selectedSlugs={selectedDomains}
          onChange={onSelectedDomainsChange}
        />
      </div>
      <AskOutputOptions selected={outputFormats} onChange={onOutputFormatsChange} />
    </>
  );
}
