/** Parse /domain-slug tokens from agent instructions (mirrors backend). */
export function parseDomainSlugsFromInstructions(text: string): string[] {
  const re = /(?<![a-zA-Z0-9:/])\/([a-z][a-z0-9_-]+)/gi;
  const seen = new Set<string>();
  const slugs: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const slug = match[1].toLowerCase();
    if (!seen.has(slug)) {
      seen.add(slug);
      slugs.push(slug);
    }
  }
  return slugs;
}
