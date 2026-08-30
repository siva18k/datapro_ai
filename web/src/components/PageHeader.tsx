export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-header flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && (
          <span className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            {description}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
