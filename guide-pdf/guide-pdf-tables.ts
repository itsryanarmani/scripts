/** GFM pipe tables: parse from markdown lines and render with PDFKit. */
export type TableBlock = { kind: "table"; header: string[]; rows: string[][] };

export type TableTheme = {
  accent: string;
  coverForeground: string;
  ink: string;
  panelFill: string;
  rule: string;
};

type TableRenderCtx = {
  doc: PDFKit.PDFDocument;
  theme: TableTheme;
  ensureSpace: (h: number) => void;
};

const FONTS = { regular: "Helvetica", bold: "Helvetica-Bold", mono: "Courier" } as const;

export function splitTableRow(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return inner.split("|").map((c) => c.trim());
}

export function isTableSeparator(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

/** If `lines[i]` starts a GFM table, consume it and return the block and next index. */
export function consumeMarkdownTable(
  lines: string[],
  i: number,
): { block: TableBlock; nextIndex: number } | null {
  const line = (lines[i] ?? "").replace(/\s+$/, "");
  if (!line.includes("|") || i + 1 >= lines.length || !isTableSeparator(lines[i + 1] ?? "")) return null;
  const header = splitTableRow(line);
  let idx = i + 1;
  const rows: string[][] = [];
  while (idx + 1 < lines.length && /^\s*\|/.test(lines[idx + 1] ?? "")) {
    idx += 1;
    rows.push(splitTableRow(lines[idx] ?? ""));
  }
  return { block: { kind: "table", header, rows }, nextIndex: idx };
}

function pageTextWidth(doc: PDFKit.PDFDocument): number {
  return doc.page.width - doc.page.margins.left - doc.page.margins.right;
}

function tableRowHeight(
  doc: PDFKit.PDFDocument,
  cells: string[],
  colW: number,
  font: keyof typeof FONTS,
  size: number,
): number {
  let max = 0;
  doc.font(FONTS[font]).fontSize(size);
  for (const cell of cells) {
    const h = doc.heightOfString(cell || " ", { width: colW - 12, lineGap: 1 });
    max = Math.max(max, h);
  }
  return Math.max(20, max + 14);
}

function drawTableBorders(
  doc: PDFKit.PDFDocument,
  x: number,
  y: number,
  width: number,
  rowHeights: number[],
  cols: number,
  colW: number,
  rule: string,
) {
  let yy = y;
  for (const rh of rowHeights) {
    doc.rect(x, yy, width, rh).strokeColor(rule).stroke();
    for (let c = 1; c < cols; c += 1) doc.moveTo(x + c * colW, yy).lineTo(x + c * colW, yy + rh).strokeColor(rule).stroke();
    yy += rh;
  }
}

export function renderTable(ctx: TableRenderCtx, block: TableBlock) {
  const { doc, theme, ensureSpace } = ctx;
  const cols = Math.max(block.header.length, 1);
  let width = pageTextWidth(doc);
  const landscape = cols >= 6;
  const margins = doc.page.margins;
  if (landscape) {
    doc.addPage({ size: "letter", layout: "landscape", margins });
    width = pageTextWidth(doc);
  }
  const colW = width / cols;
  const bodySize = cols >= 6 ? 7.5 : cols >= 4 ? 8.5 : 10;
  const headerSize = bodySize + 0.5;
  ensureSpace(60);
  const x = doc.page.margins.left;
  let y = doc.y;
  const top = y;
  const headerH = tableRowHeight(doc, block.header, colW, "bold", headerSize);
  doc.save();
  doc.rect(x, y, width, headerH).fill(theme.accent);
  doc.fillColor(theme.coverForeground).font(FONTS.bold).fontSize(headerSize);
  block.header.forEach((cell, ci) => {
    doc.text(cell, x + ci * colW + 6, y + 7, { width: colW - 12, lineGap: 1 });
  });
  const rowHeights = [headerH];
  y += headerH;
  block.rows.forEach((row, ri) => {
    const padded = [...row];
    while (padded.length < cols) padded.push("");
    const rh = tableRowHeight(doc, padded, colW, "regular", bodySize);
    rowHeights.push(rh);
    const fill = ri % 2 === 0 ? theme.panelFill : "#ffffff";
    doc.rect(x, y, width, rh).fill(fill);
    doc.fillColor(theme.ink).font(FONTS.regular).fontSize(bodySize);
    padded.forEach((cell, ci) => {
      doc.text(cell || " ", x + ci * colW + 6, y + 7, { width: colW - 12, lineGap: 1 });
    });
    y += rh;
  });
  doc.restore();
  drawTableBorders(doc, x, top, width, rowHeights, cols, colW, theme.rule);
  doc.y = y + 10;
  if (landscape) doc.addPage({ size: "letter", layout: "portrait", margins });
}
