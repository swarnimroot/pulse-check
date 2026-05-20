import type { AspectRow, BriefView, Claim, MentionView, ProductDetail } from "@/lib/types";

/**
 * Pure-function markdown renderer for the Standalone brief.
 *
 * Mirrors the A4 sheet layout in `BriefExportButton.tsx` (snapshot stats →
 * per-aspect table → top strengths → top complaints → citations) but emits
 * GFM-compatible markdown. Citation numbers are caller-provided so the body
 * `[n]` refs and the citations footer agree (BriefExportButton builds the
 * same Map for the visual sheet — passing it in keeps the two outputs
 * numerically consistent for the same view).
 */

interface BriefToMarkdownInput {
  product: ProductDetail;
  brief: BriefView;
  strengths: Claim[];
  weaknesses: Claim[];
  citedIds: string[];
  citeNumber: Map<string, number>;
  mentions: Map<string, MentionView>;
}

const ASPECT_LABELS: Record<string, string> = {
  thermals: "Thermals",
  performance: "Performance",
  keyboard: "Keyboard",
  display: "Display",
  battery: "Battery",
  build_quality: "Build",
  software_experience: "Software",
  price_value: "Price",
  support_warranty: "Support",
  aesthetics: "Aesthetics",
  portability: "Portability",
};
const ORDERED_ASPECTS = Object.keys(ASPECT_LABELS);

function fmtNum(n: number): string {
  return n.toLocaleString("en-US");
}

function fmtSentiment(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function shortSource(sourceType: string, channel: string | null): string {
  if (sourceType.startsWith("reddit")) return channel ? `r/${channel}` : "reddit";
  if (sourceType === "youtube_chunk") return channel ?? "youtube";
  if (sourceType === "article") return channel ?? "article";
  return sourceType;
}

function countAspectTones(aspects: AspectRow[]): {
  pos: number;
  neg: number;
  net: number;
  tracked: number;
} {
  let pos = 0;
  let neg = 0;
  let sumNet = 0;
  let tracked = 0;
  for (const a of aspects) {
    if (a.total_mentions === 0) continue;
    tracked += 1;
    sumNet += a.net_sentiment;
    if (a.net_sentiment > 0.1) pos += 1;
    else if (a.net_sentiment < -0.1) neg += 1;
  }
  const net = tracked > 0 ? sumNet / tracked : 0;
  return { pos, neg, net, tracked };
}

function claimText(c: Claim): string {
  if (c.header && c.header.length > 0) return c.header;
  const firstSentence = (c.claim_text.split(". ")[0] ?? c.claim_text).slice(0, 200);
  return firstSentence;
}

function claimLine(c: Claim, citeNumber: Map<string, number>): string {
  const nums = c.cited_mention_ids
    .map((id) => citeNumber.get(id))
    .filter((n): n is number => n !== undefined);
  const tail = nums.length > 0 ? ` [${nums.join(", ")}]` : "";
  return `- ${claimText(c)}${tail}`;
}

export function briefToMarkdown(input: BriefToMarkdownInput): string {
  const { product, brief, strengths, weaknesses, citedIds, citeNumber, mentions } = input;
  const stats = countAspectTones(product.aspects);
  const aspectByName = new Map<string, AspectRow>();
  for (const a of product.aspects) aspectByName.set(a.aspect, a);

  const lines: string[] = [];

  lines.push(`# ${product.display_name}`);
  lines.push("");
  lines.push(
    `*${product.brand} · ${fmtNum(product.run_meta.total_mentions)} public mentions analyzed · ${product.run_meta.window_label}*`,
  );
  lines.push("");
  lines.push(`Run: \`${brief.run_id}\``);
  lines.push("");

  // Snapshot stats
  lines.push("## Snapshot");
  lines.push("");
  lines.push("| | |");
  lines.push("|---|---|");
  lines.push(`| Public mentions | ${fmtNum(product.run_meta.total_mentions)} |`);
  lines.push(`| Positive aspects | ${stats.pos} / ${stats.tracked} |`);
  lines.push(`| Negative aspects | ${stats.neg} / ${stats.tracked} |`);
  lines.push(`| Avg net sentiment | ${fmtSentiment(stats.net)} |`);
  lines.push("");

  // Aspect snapshot (11 rows, canonical order; "(no data)" for missing)
  lines.push("## Aspect snapshot");
  lines.push("");
  lines.push("| Aspect | Net sentiment | Mentions |");
  lines.push("|---|---|---|");
  for (const aspect of ORDERED_ASPECTS) {
    const a = aspectByName.get(aspect);
    if (!a || a.total_mentions === 0) {
      lines.push(`| ${ASPECT_LABELS[aspect]} | — | 0 |`);
    } else {
      lines.push(
        `| ${ASPECT_LABELS[aspect]} | ${fmtSentiment(a.net_sentiment)} | ${fmtNum(a.total_mentions)} |`,
      );
    }
  }
  lines.push("");

  // Top strengths
  lines.push("## Top strengths");
  lines.push("");
  if (strengths.length === 0) {
    lines.push("_No high-signal strengths in this brief._");
  } else {
    for (const c of strengths) lines.push(claimLine(c, citeNumber));
  }
  lines.push("");

  // Top complaints
  lines.push("## Top complaints");
  lines.push("");
  if (weaknesses.length === 0) {
    lines.push("_No high-signal complaints in this brief._");
  } else {
    for (const c of weaknesses) lines.push(claimLine(c, citeNumber));
  }
  lines.push("");

  // Citations
  if (citedIds.length > 0) {
    lines.push("## Citations");
    lines.push("");
    for (const id of citedIds) {
      const n = citeNumber.get(id) ?? 0;
      const m = mentions.get(id);
      const source = m ? shortSource(m.source_type, m.channel) : "—";
      const author = m?.author ? ` · @${m.author}` : "";
      const date = m?.published_at ? ` · ${fmtDate(m.published_at)}` : "";
      lines.push(`${n}. ${source}${author}${date}`);
    }
    lines.push("");
  }

  lines.push("---");
  lines.push("");
  lines.push("_Every claim cites a real mention. Verbatims live in the app._");
  lines.push(`_Generated by pulse-check · ${fmtDate(new Date().toISOString())}._`);
  lines.push("");

  return lines.join("\n");
}
