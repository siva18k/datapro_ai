import type { ReactNode } from "react";

export function SidebarHint({
  hint,
  children,
  active,
  onClick,
}: {
  hint: string;
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  const className = `sidebar-hint${active ? " sidebar-hint--active" : ""}`;
  if (onClick) {
    return (
      <button type="button" className={className} data-hint={hint} title={hint} onClick={onClick}>
        {children}
      </button>
    );
  }
  return (
    <span className={className} data-hint={hint} title={hint}>
      {children}
    </span>
  );
}
