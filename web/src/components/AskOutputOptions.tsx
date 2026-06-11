export type OutputFormat = "html" | "csv" | "chart";

export const OUTPUT_FORMATS: { id: OutputFormat; label: string }[] = [
  { id: "html", label: "HTML" },
  { id: "csv", label: "CSV" },
  { id: "chart", label: "Chart" },
];

export function AskOutputOptions({
  selected,
  onChange,
  collapsed = false,
}: {
  selected: OutputFormat[];
  onChange: (next: OutputFormat[]) => void;
  collapsed?: boolean;
}) {
  const toggle = (id: OutputFormat) => {
    if (selected.includes(id)) {
      onChange(selected.filter((x) => x !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  if (collapsed) {
    const labels = selected.length
      ? selected.map((id) => OUTPUT_FORMATS.find((o) => o.id === id)?.label ?? id).join(", ")
      : "None";
    return (
      <span className="sidebar-hint" data-hint={`Output: ${labels}`} title={`Output: ${labels}`}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
        </svg>
      </span>
    );
  }

  return (
    <div className="sidebar-panel sidebar-panel-compact border-t" style={{ borderColor: "var(--color-border-light)" }}>
      <p className="sidebar-panel-title">Output</p>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {OUTPUT_FORMATS.map((opt) => (
          <label key={opt.id} className="sidebar-check">
            <input type="checkbox" checked={selected.includes(opt.id)} onChange={() => toggle(opt.id)} />
            <span>{opt.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
