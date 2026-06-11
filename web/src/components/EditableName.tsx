import { useEffect, useState } from "react";

export function EditableName({
  value,
  onSave,
  saving = false,
  className = "",
  inputClassName = "w-full max-w-md",
}: {
  value: string;
  onSave: (name: string) => void;
  saving?: boolean;
  className?: string;
  inputClassName?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  const commit = () => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === value) {
      cancel();
      return;
    }
    onSave(trimmed);
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        className={`input ${inputClassName}`}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
          if (e.key === "Escape") {
            e.preventDefault();
            cancel();
          }
        }}
        autoFocus
        disabled={saving}
        aria-label="Edit name"
      />
    );
  }

  return (
    <button
      type="button"
      className={`editable-name group ${className}`}
      onClick={() => setEditing(true)}
      title="Click to rename"
    >
      <span>{value}</span>
      <span className="editable-name-hint">Edit</span>
    </button>
  );
}
