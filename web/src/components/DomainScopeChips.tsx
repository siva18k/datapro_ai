import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function DomainScopeChips({
  selectedSlugs,
  onChange,
  className = "",
}: {
  selectedSlugs: string[];
  onChange: (slugs: string[]) => void;
  className?: string;
}) {
  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.listDomains(),
  });

  if (selectedSlugs.length === 0) return null;

  const remove = (slug: string) => {
    onChange(selectedSlugs.filter((item) => item !== slug));
  };

  return (
    <div className={`domain-scope-chips ${className}`.trim()} role="list" aria-label="Selected domains">
      {selectedSlugs.map((slug) => {
        const domain = domains?.find((item) => item.slug === slug);
        return (
          <span key={slug} className="domain-scope-chip" role="listitem">
            <span>{domain?.name ?? slug}</span>
            <button
              type="button"
              className="domain-scope-chip-remove"
              onClick={() => remove(slug)}
              aria-label={`Remove ${domain?.name ?? slug}`}
            >
              ×
            </button>
          </span>
        );
      })}
    </div>
  );
}

export function domainScopeLabel(selectedSlugs: string[], domains?: { slug: string; name: string }[]): string {
  if (selectedSlugs.length === 0) return "Auto";
  const names = selectedSlugs.map((slug) => domains?.find((d) => d.slug === slug)?.name ?? slug);
  return names.join(", ");
}
