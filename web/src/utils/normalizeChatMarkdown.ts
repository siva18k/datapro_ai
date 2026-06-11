/**
 * Normalize common LLM markdown quirks so ReactMarkdown + GFM render cleanly.
 */
export function normalizeChatMarkdown(content: string): string {
  let text = content.trim();

  // Models often collapse GFM table rows onto one line: "| A | B | | C | D |"
  text = text
    .split("\n")
    .map((line) => {
      if (!line.includes("|")) return line;
      const pipeCount = (line.match(/\|/g) ?? []).length;
      if (pipeCount < 4) return line;
      return line.replace(/\|\s+\|/g, "|\n|");
    })
    .join("\n");

  // Ensure a blank line before a table block (helps some parsers).
  text = text.replace(/([^\n])\n(\|[^\n]+\|)\n(\|[-:| ]+\|)/g, "$1\n\n$2\n$3");

  return text;
}
