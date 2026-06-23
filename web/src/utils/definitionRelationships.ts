export const RELATIONSHIPS_START = "<!-- datapro:relationships:start -->";
export const RELATIONSHIPS_END = "<!-- datapro:relationships:end -->";

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Replace or append the auto-generated relationships block in dataset definition markdown. */
export function mergeRelationshipsSection(definitionMd: string, sectionMd: string): string {
  const block = `${RELATIONSHIPS_START}\n${sectionMd.trim()}\n${RELATIONSHIPS_END}`;
  const pattern = new RegExp(
    `${escapeRegex(RELATIONSHIPS_START)}[\\s\\S]*?${escapeRegex(RELATIONSHIPS_END)}`,
  );
  if (pattern.test(definitionMd)) {
    return definitionMd.replace(pattern, block).trimEnd() + "\n";
  }
  const trimmed = definitionMd.trimEnd();
  return trimmed ? `${trimmed}\n\n${block}\n` : `${block}\n`;
}

export function hasRelationshipsSection(definitionMd: string): boolean {
  return definitionMd.includes(RELATIONSHIPS_START) && definitionMd.includes(RELATIONSHIPS_END);
}
