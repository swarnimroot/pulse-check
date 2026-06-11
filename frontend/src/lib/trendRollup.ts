/**
 * Trend rollup — aggregates per-week snapshots into coarser time buckets for
 * the Trend page chart.
 *
 * The backend stores one snapshot per ISO week (run_id = `run_<year>_w<NN>`).
 * Week view shows them raw; Month/Year views roll consecutive weeks into
 * calendar buckets. Volume is summed; net sentiment is the VOLUME-WEIGHTED
 * mean of the constituent weeks — equivalent to recomputing net over all the
 * mentions in the bucket. This keeps faith with the project's "every mention =
 * 1.0, no hidden weighting" rule: a 2-mention week never counts as much as a
 * 40-mention week.
 *
 * Pure functions only — unit-tested in trendRollup.test.ts; the Trend page and
 * TrendChart consume the output.
 */

import type { TrendSnapshot } from "@/lib/types";

export type Granularity = "week" | "month" | "year";

export interface TrendBucket {
  /** Axis label: "w24" (week), "Jun '26" (month), or "2026" (year). */
  label: string;
  /** Volume-weighted net sentiment in [-1, +1]. */
  net: number;
  /** Summed mention volume across the bucket. */
  vol: number;
}

// Canonical aspect order, matching the backend `Aspect` enum / ASPECT_LABELS in
// the Pair page. Aspects not in this list fall to the end in first-seen order.
const ASPECT_ORDER: readonly string[] = [
  "thermals",
  "performance",
  "keyboard",
  "display",
  "battery",
  "build_quality",
  "software_experience",
  "price_value",
  "support_warranty",
  "aesthetics",
  "portability",
];

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

/** Extract "w24" from a run_id like "run_2026_w24"; falls back to the run_id. */
export function weekLabelFromRunId(runId: string): string {
  const m = /_w(\d+)/.exec(runId);
  return m ? `w${m[1]}` : runId;
}

interface RawPoint {
  date: Date;
  weekLabel: string;
  net: number;
  vol: number;
}

function extractPoints(snapshots: TrendSnapshot[], aspect: string): RawPoint[] {
  const out: RawPoint[] = [];
  for (const snap of snapshots) {
    const point = snap.aspects.find((a) => a.aspect === aspect);
    // Skip weeks where the aspect drew no mentions — a 0-volume point would
    // anchor the line at net=0 and misrepresent a quiet week as neutral.
    if (!point || point.total_mentions <= 0) continue;
    out.push({
      date: new Date(snap.computed_at),
      weekLabel: weekLabelFromRunId(snap.run_id),
      net: point.net_sentiment,
      vol: point.total_mentions,
    });
  }
  return out;
}

/**
 * Roll a single aspect's weekly points into the requested granularity.
 * Assumes `snapshots` is chronological (oldest-first), as the API returns it;
 * output preserves that order.
 */
export function rollupAspect(
  snapshots: TrendSnapshot[],
  aspect: string,
  gran: Granularity,
): TrendBucket[] {
  const points = extractPoints(snapshots, aspect);
  if (gran === "week") {
    return points.map((p) => ({ label: p.weekLabel, net: round2(p.net), vol: p.vol }));
  }
  // Map preserves insertion order; since points are chronological the buckets
  // come out chronological too.
  const buckets = new Map<string, { wsum: number; vol: number; y: number; m: number }>();
  for (const p of points) {
    const y = p.date.getUTCFullYear();
    const m = p.date.getUTCMonth();
    const key = gran === "month" ? `${y}-${m}` : `${y}`;
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { wsum: 0, vol: 0, y, m };
      buckets.set(key, bucket);
    }
    bucket.wsum += p.net * p.vol;
    bucket.vol += p.vol;
  }
  return [...buckets.values()].map((b) => ({
    label: gran === "month" ? `${MONTHS[b.m]} '${String(b.y).slice(2)}` : `${b.y}`,
    net: b.vol ? round2(b.wsum / b.vol) : 0,
    vol: b.vol,
  }));
}

/** Distinct aspects present across all snapshots, in canonical order. */
export function availableAspects(snapshots: TrendSnapshot[]): string[] {
  const present = new Set<string>();
  for (const snap of snapshots) {
    for (const a of snap.aspects) present.add(a.aspect);
  }
  const ordered = ASPECT_ORDER.filter((a) => present.has(a));
  const extras = [...present].filter((a) => !ASPECT_ORDER.includes(a)).sort();
  return [...ordered, ...extras];
}
