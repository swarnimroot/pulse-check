import { describe, expect, it } from "vitest";
import {
  availableAspects,
  rollupAspect,
  weekLabelFromRunId,
} from "./trendRollup";
import type { TrendSnapshot } from "@/lib/types";

function snap(
  runId: string,
  computedAt: string,
  aspects: { aspect: string; total_mentions: number; net_sentiment: number }[],
): TrendSnapshot {
  return { run_id: runId, computed_at: computedAt, aspects };
}

// Three weeks: two in June 2026 (unequal volume), one in July 2026.
const SNAPSHOTS: TrendSnapshot[] = [
  snap("run_2026_w23", "2026-06-01T00:00:00Z", [
    { aspect: "thermals", total_mentions: 10, net_sentiment: 0.0 },
    { aspect: "battery", total_mentions: 4, net_sentiment: 0.5 },
  ]),
  snap("run_2026_w24", "2026-06-08T00:00:00Z", [
    { aspect: "thermals", total_mentions: 30, net_sentiment: 1.0 },
  ]),
  snap("run_2026_w28", "2026-07-06T00:00:00Z", [
    { aspect: "thermals", total_mentions: 5, net_sentiment: -0.4 },
  ]),
];

describe("weekLabelFromRunId", () => {
  it("extracts the week token from a run_id", () => {
    expect(weekLabelFromRunId("run_2026_w24")).toBe("w24");
    expect(weekLabelFromRunId("run_2025_w03")).toBe("w03");
  });
  it("falls back to the raw run_id when there's no week token", () => {
    expect(weekLabelFromRunId("manual_run")).toBe("manual_run");
  });
});

describe("rollupAspect — week granularity", () => {
  it("returns one bucket per snapshot carrying the aspect, labeled by week", () => {
    const out = rollupAspect(SNAPSHOTS, "thermals", "week");
    expect(out).toEqual([
      { label: "w23", net: 0.0, vol: 10 },
      { label: "w24", net: 1.0, vol: 30 },
      { label: "w28", net: -0.4, vol: 5 },
    ]);
  });

  it("skips snapshots missing the aspect or with zero mentions", () => {
    const extra: TrendSnapshot[] = [
      ...SNAPSHOTS,
      snap("run_2026_w29", "2026-07-13T00:00:00Z", [
        { aspect: "battery", total_mentions: 3, net_sentiment: 0.2 },
      ]),
      snap("run_2026_w30", "2026-07-20T00:00:00Z", [
        { aspect: "thermals", total_mentions: 0, net_sentiment: 0.0 },
      ]),
    ];
    const out = rollupAspect(extra, "thermals", "week");
    expect(out.map((b) => b.label)).toEqual(["w23", "w24", "w28"]);
  });
});

describe("rollupAspect — month granularity (volume-weighted)", () => {
  it("rolls weeks into calendar months with summed volume and weighted net", () => {
    const out = rollupAspect(SNAPSHOTS, "thermals", "month");
    // June: (0.0*10 + 1.0*30) / 40 = 0.75, vol 40. July: -0.4, vol 5.
    expect(out).toEqual([
      { label: "Jun '26", net: 0.75, vol: 40 },
      { label: "Jul '26", net: -0.4, vol: 5 },
    ]);
  });
});

describe("rollupAspect — year granularity", () => {
  it("rolls all weeks of a year into one bucket, volume-weighted", () => {
    const out = rollupAspect(SNAPSHOTS, "thermals", "year");
    // (0*10 + 1*30 + -0.4*5) / 45 = 28/45 = 0.6222… -> 0.62, vol 45.
    expect(out).toEqual([{ label: "2026", net: 0.62, vol: 45 }]);
  });
});

describe("availableAspects", () => {
  it("returns present aspects in canonical order", () => {
    expect(availableAspects(SNAPSHOTS)).toEqual(["thermals", "battery"]);
  });
  it("returns empty for no snapshots", () => {
    expect(availableAspects([])).toEqual([]);
  });
});
