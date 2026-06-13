import { DomainScopeChips } from "./DomainScopeChips";
import { IconGlobe } from "./SidebarNavIcons";

function ScopeOptionPill({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`ask-composer-pill${active ? " ask-composer-pill--active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      <span className="ask-composer-pill-icon" aria-hidden>
        {icon}
      </span>
      {label}
    </button>
  );
}

export function DomainScopePromptOptions({
  selectedSlugs,
  onChange,
}: {
  selectedSlugs: string[];
  onChange: (slugs: string[]) => void;
}) {
  const autoActive = selectedSlugs.length === 0;

  return (
    <>
      <ScopeOptionPill
        active={autoActive}
        onClick={() => onChange([])}
        icon={<IconGlobe width={14} height={14} />}
        label="Auto"
      />
      <DomainScopeChips selectedSlugs={selectedSlugs} onChange={onChange} />
    </>
  );
}
