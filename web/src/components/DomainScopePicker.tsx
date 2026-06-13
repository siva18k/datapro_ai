import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { domainScopeLabel } from "./DomainScopeChips";
import { useSidebarCollapsed } from "../context/SidebarContext";
import { SidebarHint } from "./SidebarHint";
import { IconGlobe } from "./SidebarNavIcons";

const AUTO_VALUE = "__auto__";
const ADD_PLACEHOLDER = "_add_";

export function DomainScopePicker({
  selectedSlugs,
  onChange,
  title = "Domain",
  hint = "Auto-detect when none selected",
  collapsedHintPrefix = "Domain",
}: {
  selectedSlugs: string[];
  onChange: (slugs: string[]) => void;
  title?: string;
  hint?: string;
  collapsedHintPrefix?: string;
}) {
  const collapsed = useSidebarCollapsed();
  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.listDomains(),
  });

  const available = (domains ?? []).filter((domain) => !selectedSlugs.includes(domain.slug));
  const label = domainScopeLabel(selectedSlugs, domains);
  const selectValue = selectedSlugs.length === 0 ? AUTO_VALUE : ADD_PLACEHOLDER;

  const onSelect = (value: string) => {
    if (value === AUTO_VALUE) {
      onChange([]);
      return;
    }
    if (!value || value === ADD_PLACEHOLDER || selectedSlugs.includes(value)) return;
    onChange([...selectedSlugs, value]);
  };

  if (collapsed) {
    return (
      <SidebarHint hint={`${collapsedHintPrefix}: ${label}`}>
        <IconGlobe />
      </SidebarHint>
    );
  }

  return (
    <div className="sidebar-field mb-0">
      <label className="sidebar-label">{title}</label>
      <select
        className="select"
        value={selectValue}
        onChange={(e) => onSelect(e.target.value)}
        aria-label="Domain scope"
      >
        <option value={AUTO_VALUE}>Auto</option>
        {selectedSlugs.length > 0 ? (
          <option value={ADD_PLACEHOLDER}>{label}</option>
        ) : null}
        {available.map((domain) => (
          <option key={domain.id} value={domain.slug}>
            + {domain.name}
          </option>
        ))}
      </select>
      {hint ? (
        <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
