#!/usr/bin/env bun
/**
 * Render guide PDFs: full-bleed cover, table of contents, tables, and themed
 * sections. Pure PDFKit (no browser) so CI can build them. English WinAnsi.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export type Guide = {
  slug: string;
  title: string;
  description: string;
  country: string | null;
  updated: string;
  body: string;
  sources: { label: string; url: string }[];
  faq: { q: string; a: string }[];
};
import PDFDocument from "pdfkit";

export type GuidePdfTheme = {
  coverBackground: string;
  coverForeground: string;
  accent: string;
  ink: string;
  muted: string;
  rule: string;
  panelFill: string;
  publisherLine?: string;
};

export const DEFAULT_GUIDE_PDF_THEME: GuidePdfTheme = {
  coverBackground: "#1e3a5f",
  coverForeground: "#ffffff",
  accent: "#c45c26",
  ink: "#1c1917",
  muted: "#57534e",
  rule: "#e7e5e4",
  panelFill: "#f5f5f4",
};

export function themeFromSeed(seed: string, publisherLine?: string): GuidePdfTheme {
  return { ...DEFAULT_GUIDE_PDF_THEME, coverBackground: seed, accent: seed, publisherLine };
}

type Config = { name: string; domain: string; defaultLocale: string };

type Block =
  | { kind: "h"; level: 1 | 2 | 3; text: string }
  | { kind: "p"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }

type TocEntry = { title: string; page: number };

type Run = { text: string; bold?: boolean; italic?: boolean; link?: string; mono?: boolean };

const FONTS = { regular: "Helvetica", bold: "Helvetica-Bold", italic: "Helvetica-Oblique", mono: "Courier" } as const;

type RenderCtx = { doc: PDFKit.PDFDocument; theme: GuidePdfTheme; width: number; ensureSpace: (h: number) => void };



export function markdownBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/<!--[\s\S]*?-->/g, "").split(/\r?\n/);
  const blocks: Block[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] | null = null;
  let code: { fence: string; lines: string[] } | null = null;

  const flushPara = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push({ kind: "list", ordered: list.ordered, items: list.items });
    list = null;
  };
  const flushQuote = () => {
    if (quote?.length) blocks.push({ kind: "quote", text: quote.join(" ") });
    quote = null;
  };
  const flush = () => {
    flushPara();
    flushList();
    flushQuote();
  };

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i] ?? "";
    const line = raw.replace(/\s+$/, "");
    if (code) {
      if (line.startsWith(code.fence)) {
        blocks.push({ kind: "code", text: code.lines.join("\n") });
        code = null;
      } else code.lines.push(raw);
      continue;
    }
    const fence = /^(`{3,}|~{3,})/.exec(line);
    if (fence) {
      flush();
      code = { fence: fence[1]!, lines: [] };
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: "h", level: heading[1]!.length as 1 | 2 | 3, text: heading[2]! });
      continue;
    }
    const item = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      flushPara();
      flushQuote();
      const ordered = /^\s*\d+[.)]\s/.test(line);
      if (!list || list.ordered !== ordered) flushList();
      (list ??= { ordered, items: [] }).items.push(item[1]!);
      continue;
    }
    const quoteLine = /^\s*>\s?(.*)$/.exec(line);
    if (quoteLine) {
      flushPara();
      flushList();
      (quote ??= []).push(quoteLine[1]!);
      continue;
    }
    if (/^\s*(?:[-*_]\s*){3,}$/.test(line)) {
      flush();
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    if (list && /^\s+\S/.test(raw)) {
      const last = list.items.length - 1;
      if (last >= 0) {
        list.items[last] = `${list.items[last]} ${line.trim()}`;
        continue;
      }
    }
    para.push(line.trim());
  }
  if (code) blocks.push({ kind: "code", text: code.lines.join("\n") });
  flush();
  return blocks.filter((b) => {
    if (b.kind === "list") return b.items.length > 0;
    return "text" in b ? b.text.trim() !== "" : true;
  });
}

function inlineRuns(text: string): Run[] {
  const runs: Run[] = [];
  const re = /(\*\*|__)(.+?)\1|\*([^*\n]+)\*|_([^_\n]+)_|`([^`\n]+)`|\[([^\]]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>)]+)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) runs.push({ text: text.slice(last, m.index) });
    const [, , bold, star, under, code, linkText, href, bare] = m;
    if (bold !== undefined) runs.push({ text: bold, bold: true });
    else if (star !== undefined) runs.push({ text: star, italic: true });
    else if (under !== undefined) runs.push({ text: under, italic: true });
    else if (code !== undefined) runs.push({ text: code, mono: true });
    else if (linkText !== undefined) runs.push({ text: linkText, link: href });
    else if (bare !== undefined) runs.push({ text: bare, link: bare });
    last = m.index! + m[0].length;
  }
  if (last < text.length) runs.push({ text: text.slice(last) });
  return runs;
}

function currentPageIndex(doc: PDFKit.PDFDocument): number {
  const range = doc.bufferedPageRange();
  return range.start + range.count - 1;
}

function writeRuns(
  doc: PDFKit.PDFDocument,
  runs: Run[],
  theme: GuidePdfTheme,
  opts: { indent?: number; base?: keyof typeof FONTS; color?: string } = {},
) {
  const ink = opts.color ?? theme.ink;
  doc.font(FONTS[opts.base ?? "regular"]).fillColor(ink);
  runs.forEach((run, i) => {
    const font = run.mono ? "mono" : run.bold ? "bold" : run.italic ? "italic" : (opts.base ?? "regular");
    const link = run.link ?? undefined;
    doc
      .font(FONTS[font])
      .fillColor(link ? theme.accent : ink)
      .text(run.text, { continued: i < runs.length - 1, link, underline: Boolean(link), indent: opts.indent });
  });
}

function renderCover(doc: PDFKit.PDFDocument, guide: Guide, config: Config, theme: GuidePdfTheme) {
  const h = doc.page.height;
  const w = doc.page.width;
  const pad = 72;
  doc.save();
  doc.rect(0, 0, w, h).fill(theme.coverBackground);
  let y = h * 0.22;
  doc.fillColor(theme.coverForeground).font(FONTS.bold).fontSize(11).text("GUIDE", pad, y, { characterSpacing: 2 });
  y += 28;
  doc.font(FONTS.bold).fontSize(32).text(guide.title, pad, y, { width: w - pad * 2, lineGap: 4 });
  y = doc.y + 20;
  doc.font(FONTS.italic).fontSize(14).fillColor(theme.coverForeground).text(guide.description, pad, y, { width: w - pad * 2 });
  y = doc.y + 24;
  const when = new Intl.DateTimeFormat(config.defaultLocale, { dateStyle: "long", timeZone: "UTC" }).format(
    new Date(`${guide.updated}T00:00:00Z`),
  );
  doc.font(FONTS.regular).fontSize(11).text(`Updated ${when}`, pad, y);
  const line = theme.publisherLine ?? config.name;
  doc.font(FONTS.regular).fontSize(10).text(line, pad, h - 56, { width: w - pad * 2 });
  doc.fontSize(10).text(config.domain, pad, h - 40, { width: w - pad * 2 });
  doc.restore();
  doc.addPage();
}

function renderTocPage(doc: PDFKit.PDFDocument, entries: TocEntry[], theme: GuidePdfTheme, width: number, tocPageIndex: number) {
  doc.switchToPage(tocPageIndex);
  const left = doc.page.margins.left;
  let y = doc.page.margins.top;
  doc.font(FONTS.bold).fontSize(22).fillColor(theme.ink).text("Contents", left, y);
  y = doc.y + 16;
  doc.moveTo(left, y).lineTo(left + width, y).strokeColor(theme.rule).stroke();
  y += 20;
  for (const entry of entries) {
    doc.font(FONTS.regular).fontSize(12).fillColor(theme.ink);
    const titleWidth = width * 0.78;
    doc.text(entry.title, left, y, { width: titleWidth, continued: true, lineBreak: false });
    const dots = "   " + "·".repeat(Math.max(2, 36 - Math.min(36, entry.title.length)));
    doc.text(dots, { continued: true, lineBreak: false });
    doc.fillColor(theme.accent).text(String(entry.page), { align: "right", width });
    y = doc.y + 10;
    if (y > doc.page.height - doc.page.margins.bottom - 40) {
      doc.addPage();
      y = doc.page.margins.top;
    }
  }
}




function renderBlocks(ctx: RenderCtx, guide: Guide, blocks: Block[], tocEntries: TocEntry[]) {
  const { doc, theme, width, ensureSpace } = ctx;
  for (const block of blocks) {
    if (block.kind === "h") {
      if (block.level === 1 && block.text.trim() === guide.title.trim()) continue;
      if (block.level === 2) tocEntries.push({ title: block.text, page: currentPageIndex(doc) + 1 });
      ensureSpace(34);
      doc.moveDown(block.level <= 2 ? 0.7 : 0.4);
      if (block.level === 2) {
        const y = doc.y;
        doc.save();
        doc.rect(doc.page.margins.left, y - 2, 4, 20).fill(theme.accent);
        doc.restore();
        doc.x = doc.page.margins.left + 14;
      }
      if (block.level === 3) {
        const y0 = doc.y;
        doc.save();
        doc.rect(doc.page.margins.left, y0, width, 22).fill(theme.panelFill);
        doc.restore();
        doc.y = y0 + 5;
      }
      doc.font(FONTS.bold).fontSize(block.level <= 2 ? 16 : 12.5).fillColor(block.level === 2 ? theme.accent : theme.ink).text(block.text, {
        width: block.level === 2 ? width - 14 : width,
      });
      doc.x = doc.page.margins.left;
      doc.moveDown(0.35);
    } else if (block.kind === "p") {
      ensureSpace(16);
      doc.fontSize(11);
      writeRuns(doc, inlineRuns(block.text), theme);
      doc.moveDown(0.55);
    } else if (block.kind === "list") {
      doc.moveDown(0.15);
      block.items.forEach((item, i) => {
        ensureSpace(16);
        doc.fontSize(11);
        if (block.ordered) {
          const cy = doc.y + 4;
          const cx = doc.page.margins.left + 8;
          doc.save();
          doc.circle(cx, cy, 8).fill(theme.accent);
          doc.fillColor(theme.coverForeground).font(FONTS.bold).fontSize(9).text(String(i + 1), cx - 4, cy - 5, { width: 8, align: "center" });
          doc.restore();
          doc.x = doc.page.margins.left + 22;
          writeRuns(doc, inlineRuns(item), theme);
          doc.x = doc.page.margins.left;
        } else {
          writeRuns(doc, [{ text: "•  ", bold: true }, ...inlineRuns(item)], theme);
        }
        doc.moveDown(0.15);
      });
      doc.moveDown(0.4);
    } else if (block.kind === "quote") {
      ensureSpace(48);
      const y = doc.y;
      doc.save();
      doc.rect(doc.page.margins.left, y, width, 4).fill(theme.accent);
      doc.roundedRect(doc.page.margins.left, y + 8, width, 40, 4).fill(theme.panelFill);
      doc.restore();
      doc.y = y + 16;
      doc.fontSize(11);
      writeRuns(doc, inlineRuns(block.text), theme, { base: "italic", indent: 8 });
      doc.y = y + 56;
      doc.moveDown(0.4);
    } else {
      ensureSpace(16);
      doc.font(FONTS.mono).fontSize(9.5).fillColor(theme.ink).text(block.text, { width });
      doc.moveDown(0.55);
    }
  }
}

export function renderGuidePdf(
  guide: Guide,
  config: Config,
  out: string,
  theme: GuidePdfTheme = DEFAULT_GUIDE_PDF_THEME,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument({
      size: "letter",
      margins: { top: 72, bottom: 72, left: 72, right: 72 },
      bufferPages: true,
      info: { Title: guide.title, Author: config.name, Subject: guide.description, Creator: config.name },
    });
    const chunks: Buffer[] = [];
    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => {
      mkdirSync(join(out, ".."), { recursive: true });
      writeFileSync(out, Buffer.concat(chunks));
      resolve(out);
    });
    doc.on("error", reject);

    const width = doc.page.width - doc.page.margins.left - doc.page.margins.right;
    const blocks = markdownBlocks(guide.body);
    const tocEntries: TocEntry[] = [];

    renderCover(doc, guide, config, theme);
    const tocPageIndex = currentPageIndex(doc);
    doc.font(FONTS.regular).fontSize(1).fillColor(theme.ink).text(" ", doc.page.margins.left, doc.page.margins.top);
    doc.addPage();

    const ensureSpace = (h: number) => {
      if (doc.y + h > doc.page.height - doc.page.margins.bottom) doc.addPage();
    };
    const ctx: RenderCtx = { doc, theme, width, ensureSpace };

    renderBlocks(ctx, guide, blocks, tocEntries);

    if (guide.country) {
      doc.moveDown(0.5);
      doc
        .font(FONTS.regular)
        .fontSize(10)
        .fillColor(theme.muted)
        .text(`This guide is about ${countryName(guide.country, config.defaultLocale)}.`);
    }

    renderTocPage(doc, tocEntries, theme, width, tocPageIndex);

    const range = doc.bufferedPageRange();
    const y = doc.page.height - 50;
    for (let i = range.start; i < range.start + range.count; i += 1) {
      doc.switchToPage(i);
      if (i === 0) continue;
      const bottom = doc.page.margins.bottom;
      doc.page.margins.bottom = 0;
      doc.font(FONTS.regular).fontSize(9).fillColor(theme.muted);
      doc.text(config.domain, doc.page.margins.left, y, { lineBreak: false });
      doc.text(`page ${i + 1} of ${range.count}`, doc.page.margins.left, y, { align: "right", lineBreak: false, width });
      doc.page.margins.bottom = bottom;
    }

    doc.end();
  });
}

