import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useSidebarCollapsed } from "../context/SidebarContext";
import { AskOutputOptions, type OutputFormat } from "./AskOutputOptions";
import { SidebarHint } from "./SidebarHint";
import { IconDebug, IconGlobe, IconSearch } from "./SidebarNavIcons";

export function AskRetrievalPanel({
  topK,
  onTopKChange,
  domainOverride,
  onDomainOverrideChange,
  outputFormats,
  onOutputFormatsChange,
  debugMode,
  onDebugModeChange,
}: {
  topK: number;
  onTopKChange: (value: number) => void;
  domainOverride: string;
  onDomainOverrideChange: (value: string) => void;
  outputFormats: OutputFormat[];
  onOutputFormatsChange: (value: OutputFormat[]) => void;
  debugMode: boolean;
  onDebugModeChange: (value: boolean) => void;
}) {
  const collapsed = useSidebarCollapsed();
  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.listDomains(),
  });

  const domainLabel =
    domainOverride
      ? domains?.find((d) => d.slug === domainOverride)?.name ?? domainOverride
      : "Auto";

  if (collapsed) {
    return (
      <div className="sidebar-collapsed-stack">
        <SidebarHint hint={`Retrieval · Top K ${topK}`}>
          <IconSearch />
        </SidebarHint>
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
        <div className="sidebar-field">
          <label className="sidebar-label">Top K</label>
          <input
            type="number"
            className="input"
            min={1}
            max={8}
            value={topK}
            onChange={(e) => onTopKChange(Number(e.target.value))}
          />
        </div>
        <div className="sidebar-field mb-0">
          <label className="sidebar-label">Domain</label>
          <select className="select" value={domainOverride} onChange={(e) => onDomainOverrideChange(e.target.value)}>
            <option value="">Auto</option>
            {domains?.map((d) => (
              <option key={d.id} value={d.slug}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <label className="sidebar-check mt-3 flex cursor-pointer items-center gap-2 text-sm text-zinc-600">
          <input
            type="checkbox"
            checked={debugMode}
            onChange={(e) => onDebugModeChange(e.target.checked)}
          />
          Debug mode
        </label>
        {debugMode && (
          <p className="mt-1 text-xs text-zinc-500">Sources &amp; chunk IDs per answer</p>
        )}
      </div>
      <AskOutputOptions selected={outputFormats} onChange={onOutputFormatsChange} />
    </>
  );
}
