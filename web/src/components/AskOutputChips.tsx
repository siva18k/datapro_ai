import { useState } from "react";
import { OUTPUT_FORMATS, type OutputFormat } from "./AskOutputOptions";
import { generateAskOutput, type ExportPayload } from "../utils/askExport";

export function AskOutputChips({
  formats,
  payload,
}: {
  formats: OutputFormat[];
  payload: ExportPayload;
}) {
  const [loading, setLoading] = useState<OutputFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!formats.length) return null;

  const onGenerate = async (format: OutputFormat) => {
    setError(null);
    setLoading(format);
    try {
      await generateAskOutput(format, payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="mt-3">
      <p className="mb-1.5 text-xs font-medium" style={{ color: "var(--color-text-muted)" }}>
        Generate output
      </p>
      <div className="flex flex-wrap gap-2">
        {formats.map((id) => {
          const opt = OUTPUT_FORMATS.find((o) => o.id === id);
          return (
            <button
              key={id}
              type="button"
              className="output-chip"
              disabled={loading !== null}
              onClick={() => onGenerate(id)}
            >
              {loading === id ? "Generating…" : `Generate ${opt?.label ?? id}`}
            </button>
          );
        })}
      </div>
      {error && <p className="alert-error mt-2 text-xs">{error}</p>}
    </div>
  );
}
