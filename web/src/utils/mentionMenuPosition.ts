export type MentionMenuPos = {
  top: number;
  left: number;
  placement: "above" | "below";
};

const MENU_WIDTH = 240;
const MENU_MAX_HEIGHT = 280;

/** Viewport-fixed position for @ / @@ autocomplete anchored to a zero-width marker span. */
export function computeMentionMenuPos(anchor: HTMLElement): MentionMenuPos {
  const rect = anchor.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  const placement =
    spaceBelow < MENU_MAX_HEIGHT && spaceAbove > spaceBelow ? "above" : "below";
  const left = Math.min(
    Math.max(8, rect.left),
    window.innerWidth - MENU_WIDTH - 8,
  );
  const top = placement === "below" ? rect.bottom + 4 : rect.top - 4;
  return { top, left, placement };
}
