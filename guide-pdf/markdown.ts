export function splitFrontmatter(text: string): { yaml: string; body: string } | null {
  const match = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text);
  return match ? { yaml: match[1] ?? "", body: match[2] ?? "" } : null;
}
