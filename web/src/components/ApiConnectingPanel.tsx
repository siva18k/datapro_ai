type Props = {
  title?: string;
};

export function ApiConnectingPanel({ title = "Connecting to API server…" }: Props) {
  return (
    <div className="card card-pad max-w-xl" role="status" aria-live="polite">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
        Checking every few seconds. This may take up to 10 seconds while the server loads.
      </p>
    </div>
  );
}
