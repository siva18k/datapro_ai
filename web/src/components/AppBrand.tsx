export function AppBrand({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`app-brand app-brand--${size}`} aria-label="DATA Pro">
      <span className="app-brand-gradient">DATA</span>
      <span className="app-brand-gradient app-brand-pro">Pro</span>
    </span>
  );
}
