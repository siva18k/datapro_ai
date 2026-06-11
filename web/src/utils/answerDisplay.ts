const SOURCE_CITATION_RE = /\s*\[[^\]]+ - [^\]]+\]/g;

/** Remove inline [source_file - chunk_id] citations from assistant answers. */
export function stripSourceCitations(text: string): string {
  return text.replace(SOURCE_CITATION_RE, "").replace(/\n{3,}/g, "\n\n").trim();
}
