import type {
  BriefView,
  MentionView,
  PairAspectRow,
  PairBriefNarrative,
  PairResponse,
} from "@/lib/types";

/**
 * Pure-function markdown renderer for the Pair comparative brief.
 *
 * Mirrors `exportMarkdown.briefToMarkdown` for the standalone side, but the
 * shape diverges where the pair brief differs from the A1 brief:
 *   - Snapshot is a 3-column comparison instead of a 2-column stat list
 *   - Aspect comparison shows primary / competitor / delta per row
 *   - Contrast paragraph replaces summary (single italic paragraph)
 *   - "Where X leads" + "Where Y leads" bullets replace strengths / complaints
 *     (top 3 per side ranked by abs(delta), threshold 0.10 — same rule as
 *     the in-app scorecard's leader-highlight)
 *
 * Citation numbering: contrast cites lead the `[n]` numbering (reading
 * order), then primary-leader cites, then competitor-leader cites; each
 * leader bullet cites up to 2 mention_ids from its leading side.
 */

export const PAIR_LEAD_THRESHOLD = 0.1;
const LEADER_CITE_LIMIT = 2;
const TOP_LEADERS_PER_SIDE = 3;

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

interface PairToMarkdownInput {
  pair: PairResponse;
  brief: BriefView;
  mentions: Map<string, MentionView>;
}

export interface PairLeaderBullet {
  row: PairAspectRow;
  side: "primary" | "competitor";
  citedMentionIds: string[];
}

export interface PairExportLeaders {
  primary: PairLeaderBullet[];
  competitor: PairLeaderBullet[];
}

function aspectLabel(a: string): string {
  return ASPECT_LABELS[a] ?? a;
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

/**
 * Pull the top `TOP_LEADERS_PER_SIDE` leader rows per side from the pair
 * response, filtered by the lead threshold and sorted by abs(delta) desc.
 * Each bullet carries up to `LEADER_CITE_LIMIT` mention_ids from its
 * leading side's mention pool (deterministic — first N from the array).
 */
export function computePairLeaders(pair: PairResponse): PairExportLeaders {
  const primaryLeaders: PairLeaderBullet[] = [];
  const competitorLeaders: PairLeaderBullet[] = [];
  for (const row of pair.rows) {
    if (row.leader === "tie") continue;
    if (Math.abs(row.delta) <= PAIR_LEAD_THRESHOLD) continue;
    const leadingCell = row.leader === "primary" ? row.primary : row.competitor;
    const cited = leadingCell ? leadingCell.mention_ids.slice(0, LEADER_CITE_LIMIT) : [];
    const bullet: PairLeaderBullet = {
      row,
      side: row.leader,
      citedMentionIds: cited,
    };
    if (row.leader === "primary") primaryLeaders.push(bullet);
    else competitorLeaders.push(bullet);
  }
  const byAbsDelta = (a: PairLeaderBullet, b: PairLeaderBullet): number =>
    Math.abs(b.row.delta) - Math.abs(a.row.delta);
  primaryLeaders.sort(byAbsDelta);
  competitorLeaders.sort(byAbsDelta);
  return {
    primary: primaryLeaders.slice(0, TOP_LEADERS_PER_SIDE),
    competitor: competitorLeaders.slice(0, TOP_LEADERS_PER_SIDE),
  };
}

/**
 * Reading-order union of all mention ids that will get a `[n]` ref:
 *   contrast → primary leader bullets → competitor leader bullets.
 * Dedup keeps the first appearance so the numbering matches the rendered
 * order in the body.
 */
export function buildPairCitedIds(
  contrastIds: string[],
  leaders: PairExportLeaders,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (id: string): void => {
    if (seen.has(id)) return;
    seen.add(id);
    out.push(id);
  };
  for (const id of contrastIds) push(id);
  for (const bullet of leaders.primary) {
    for (const id of bullet.citedMentionIds) push(id);
  }
  for (const bullet of leaders.competitor) {
    for (const id of bullet.citedMentionIds) push(id);
  }
  return out;
}

interface PairSnapshot {
  primaryLeads: number;
  competitorLeads: number;
  ties: number;
  totalAspects: number;
  primaryAvgNet: number;
  competitorAvgNet: number;
  primaryCoverage: number;
  competitorCoverage: number;
}

function summarizePair(pair: PairResponse): PairSnapshot {
  let primarySum = 0;
  let primaryCount = 0;
  let competitorSum = 0;
  let competitorCount = 0;
  for (const row of pair.rows) {
    if (row.primary && row.primary.total_mentions > 0) {
      primarySum += row.primary.net_sentiment;
      primaryCount += 1;
    }
    if (row.competitor && row.competitor.total_mentions > 0) {
      competitorSum += row.competitor.net_sentiment;
      competitorCount += 1;
    }
  }
  return {
    primaryLeads: pair.primary_leads_count,
    competitorLeads: pair.competitor_leads_count,
    ties: pair.ties_count,
    totalAspects: pair.rows.length,
    primaryAvgNet: primaryCount > 0 ? primarySum / primaryCount : 0,
    competitorAvgNet: competitorCount > 0 ? competitorSum / competitorCount : 0,
    primaryCoverage: primaryCount,
    competitorCoverage: competitorCount,
  };
}

function leaderBulletLine(
  bullet: PairLeaderBullet,
  citeNumber: Map<string, number>,
): string {
  const { row } = bullet;
  const priNet = row.primary ? fmtSentiment(row.primary.net_sentiment) : "—";
  const compNet = row.competitor ? fmtSentiment(row.competitor.net_sentiment) : "—";
  const delta = `+${Math.abs(row.delta).toFixed(2)}`;
  const nums = bullet.citedMentionIds
    .map((id) => citeNumber.get(id))
    .filter((n): n is number => n !== undefined);
  const tail = nums.length > 0 ? ` [${nums.join(", ")}]` : "";
  return `- **${aspectLabel(row.aspect)}**: net ${priNet} vs ${compNet} (Δ ${delta})${tail}`;
}

export function pairBriefToMarkdown(input: PairToMarkdownInput): string {
  const { pair, brief, mentions } = input;
  const narrative = brief.narrative as unknown as PairBriefNarrative;
  const contrast = narrative.contrast;
  const leaders = computePairLeaders(pair);
  const citedIds = buildPairCitedIds(contrast.cited_mention_ids, leaders);
  const citeNumber = new Map<string, number>();
  citedIds.forEach((id, i) => citeNumber.set(id, i + 1));
  const stats = summarizePair(pair);

  const lines: string[] = [];
  const heading = `${pair.primary.display_name} vs ${pair.competitor.display_name}`;
  lines.push(`# ${heading}`);
  lines.push("");
  lines.push(
    `*${pair.primary.brand} vs ${pair.competitor.brand} · head-to-head on ${stats.totalAspects} aspects · generated ${fmtDate(pair.generated_at)}*`,
  );
  lines.push("");
  if (pair.run_id) lines.push(`Run: \`${pair.run_id}\``);
  else lines.push(`Brief: \`${brief.run_id}\``);
  lines.push("");

  // Snapshot — 3-col comparison.
  lines.push("## Snapshot");
  lines.push("");
  lines.push(`|  | ${pair.primary.display_name} | ${pair.competitor.display_name} |`);
  lines.push("|---|---|---|");
  lines.push(
    `| Aspects led | ${stats.primaryLeads} / ${stats.totalAspects} | ${stats.competitorLeads} / ${stats.totalAspects} |`,
  );
  lines.push(
    `| Aspects with data | ${stats.primaryCoverage} / ${stats.totalAspects} | ${stats.competitorCoverage} / ${stats.totalAspects} |`,
  );
  lines.push(
    `| Avg net sentiment | ${fmtSentiment(stats.primaryAvgNet)} | ${fmtSentiment(stats.competitorAvgNet)} |`,
  );
  lines.push("");
  lines.push(`_Ties: ${stats.ties} / ${stats.totalAspects} (net within ±${PAIR_LEAD_THRESHOLD.toFixed(2)})._`);
  lines.push("");

  // Aspect comparison — 11 rows in PairResponse order.
  lines.push("## Aspect comparison");
  lines.push("");
  lines.push(`| Aspect | ${pair.primary.display_name} | ${pair.competitor.display_name} | Δ |`);
  lines.push("|---|---|---|---|");
  for (const row of pair.rows) {
    const priCell = row.primary && row.primary.total_mentions > 0
      ? fmtSentiment(row.primary.net_sentiment)
      : "—";
    const compCell = row.competitor && row.competitor.total_mentions > 0
      ? fmtSentiment(row.competitor.net_sentiment)
      : "—";
    let deltaCell = "—";
    if (row.leader === "tie") {
      deltaCell = "tie";
    } else if (row.primary && row.competitor) {
      const sign = row.leader === "primary" ? "+" : "−";
      deltaCell = `${sign}${Math.abs(row.delta).toFixed(2)}`;
    }
    lines.push(`| ${aspectLabel(row.aspect)} | ${priCell} | ${compCell} | ${deltaCell} |`);
  }
  lines.push("");

  // Contrast paragraph (italic; mirrors A1's summary block).
  if (contrast.text.length > 0) {
    const nums = contrast.cited_mention_ids
      .map((id) => citeNumber.get(id))
      .filter((n): n is number => n !== undefined);
    const tail = nums.length > 0 ? ` [${nums.join(", ")}]` : "";
    lines.push("## Contrast");
    lines.push("");
    lines.push(`*${contrast.text}*${tail}`);
    lines.push("");
  }

  // Where {primary} leads.
  lines.push(`## Where ${pair.primary.display_name} leads`);
  lines.push("");
  if (leaders.primary.length === 0) {
    lines.push(`_No aspects where ${pair.primary.display_name} leads by more than ${PAIR_LEAD_THRESHOLD.toFixed(2)}._`);
  } else {
    for (const bullet of leaders.primary) {
      lines.push(leaderBulletLine(bullet, citeNumber));
    }
  }
  lines.push("");

  // Where {competitor} leads.
  lines.push(`## Where ${pair.competitor.display_name} leads`);
  lines.push("");
  if (leaders.competitor.length === 0) {
    lines.push(`_No aspects where ${pair.competitor.display_name} leads by more than ${PAIR_LEAD_THRESHOLD.toFixed(2)}._`);
  } else {
    for (const bullet of leaders.competitor) {
      lines.push(leaderBulletLine(bullet, citeNumber));
    }
  }
  lines.push("");

  // Citations.
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
