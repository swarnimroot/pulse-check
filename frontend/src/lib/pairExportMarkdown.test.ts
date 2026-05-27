import { describe, expect, it } from "vitest";
import {
  PAIR_LEAD_THRESHOLD,
  buildPairCitedIds,
  computePairLeaders,
  pairBriefToMarkdown,
} from "./pairExportMarkdown";
import type {
  BriefView,
  MentionView,
  PairAspectCell,
  PairAspectRow,
  PairResponse,
} from "@/lib/types";

function makeCell(overrides: Partial<PairAspectCell> = {}): PairAspectCell {
  return {
    total_mentions: 10,
    net_sentiment: 0.2,
    mention_ids: ["m_default"],
    ...overrides,
  };
}

function makeRow(overrides: Partial<PairAspectRow> = {}): PairAspectRow {
  return {
    aspect: "thermals",
    primary: null,
    competitor: null,
    delta: 0,
    leader: "tie",
    ...overrides,
  };
}

function makePair(overrides: Partial<PairResponse> = {}): PairResponse {
  return {
    primary: {
      product_id: "alienware_m18_r2",
      display_name: "Alienware m18 R2",
      brand: "Alienware",
    },
    competitor: {
      product_id: "rog_strix_g18",
      display_name: "ROG Strix G18",
      brand: "ASUS",
    },
    aspects: ["thermals", "performance"],
    rows: [],
    primary_leads_count: 0,
    competitor_leads_count: 0,
    ties_count: 0,
    run_id: "run_wave5_v1",
    generated_at: "2026-05-20T12:00:00Z",
    latest_pair_brief_id: 99,
    ...overrides,
  };
}

function makeBrief(overrides: Partial<BriefView> = {}): BriefView {
  // Pair-brief narrative is carried inside BriefView.narrative (typed as A1
  // shape for convenience; pair consumers cast at runtime). Test fixtures
  // therefore go through `unknown` to mock the pair-narrative shape without
  // tripping the static A1 type guard.
  const pairNarrative = {
    brief_title: "Alienware m18 R2 vs ROG Strix G18 — pair contrast",
    contrast: {
      text: "Alienware leans premium-build with stronger keyboard signal; the Strix wins on price and thermals balance.",
      cited_mention_ids: ["m1", "m2", "m3"],
    },
  };
  return {
    brief_id: 99,
    run_id: "run_wave5_v1",
    scope_type: "aspect_2_pair",
    scope_id: "alienware_m18_r2_vs_rog_strix_g18",
    prompt_version: "pair_brief_v1",
    model: "claude-sonnet-4-6",
    generated_at: "2026-05-26T12:00:00Z",
    // Casting through unknown — see comment above.
    narrative: pairNarrative as unknown as BriefView["narrative"],
    ...overrides,
  };
}

function makeMention(id: string, overrides: Partial<MentionView> = {}): MentionView {
  return {
    mention_id: id,
    source_type: "reddit_post",
    channel: "GamingLaptops",
    author: "user123",
    published_at: "2026-04-15T10:00:00Z",
    raw_text: "...",
    url: "https://example.com",
    verified: false,
    upvotes: 12,
    rating: null,
    aspect_tags: [],
    tombstoned_at: null,
    tombstone_reason: null,
    ...overrides,
  };
}

describe("computePairLeaders", () => {
  it("filters out ties and rows below the threshold", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "thermals",
          primary: makeCell({ net_sentiment: 0.3 }),
          competitor: makeCell({ net_sentiment: 0.25 }),
          delta: 0.05,
          leader: "tie",
        }),
        makeRow({
          aspect: "build_quality",
          primary: makeCell({ net_sentiment: 0.5, mention_ids: ["m1", "m2", "m3"] }),
          competitor: makeCell({ net_sentiment: -0.1 }),
          delta: 0.6,
          leader: "primary",
        }),
      ],
    });
    const leaders = computePairLeaders(pair);
    expect(leaders.primary).toHaveLength(1);
    expect(leaders.primary[0].row.aspect).toBe("build_quality");
    expect(leaders.competitor).toHaveLength(0);
  });

  it("sorts by abs(delta) desc and caps at 3 per side", () => {
    const rows: PairAspectRow[] = [];
    for (let i = 0; i < 5; i++) {
      rows.push(
        makeRow({
          aspect: `aspect_${i}`,
          primary: makeCell({ net_sentiment: 0.5, mention_ids: [`p${i}`] }),
          competitor: makeCell({ net_sentiment: 0 }),
          delta: 0.2 + i * 0.05,
          leader: "primary",
        }),
      );
    }
    const leaders = computePairLeaders(makePair({ rows }));
    expect(leaders.primary).toHaveLength(3);
    expect(leaders.primary.map((b) => b.row.aspect)).toEqual([
      "aspect_4",
      "aspect_3",
      "aspect_2",
    ]);
  });

  it("uses up to 2 mention_ids from the leading side per bullet", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "battery",
          primary: makeCell({ net_sentiment: 0.1 }),
          competitor: makeCell({
            net_sentiment: 0.4,
            mention_ids: ["c1", "c2", "c3", "c4"],
          }),
          delta: -0.3,
          leader: "competitor",
        }),
      ],
    });
    const leaders = computePairLeaders(pair);
    expect(leaders.competitor[0].citedMentionIds).toEqual(["c1", "c2"]);
  });
});

describe("buildPairCitedIds", () => {
  it("dedups while preserving reading order: contrast → primary → competitor", () => {
    const ids = buildPairCitedIds(
      ["m1", "m2"],
      {
        primary: [
          { row: makeRow(), side: "primary", citedMentionIds: ["m2", "m3"] },
        ],
        competitor: [
          { row: makeRow(), side: "competitor", citedMentionIds: ["m3", "m4"] },
        ],
      },
    );
    expect(ids).toEqual(["m1", "m2", "m3", "m4"]);
  });
});

describe("pairBriefToMarkdown", () => {
  it("renders the comparative H1 + metadata line + run id", () => {
    const md = pairBriefToMarkdown({
      pair: makePair(),
      brief: makeBrief(),
      mentions: new Map(),
    });
    expect(md).toContain("# Alienware m18 R2 vs ROG Strix G18");
    expect(md).toContain("*Alienware vs ASUS · head-to-head on 0 aspects");
    expect(md).toContain("Run: `run_wave5_v1`");
  });

  it("renders 3-col snapshot with leads / coverage / avg-net per side", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "thermals",
          primary: makeCell({ net_sentiment: 0.4 }),
          competitor: makeCell({ net_sentiment: -0.2 }),
          delta: 0.6,
          leader: "primary",
        }),
        makeRow({
          aspect: "performance",
          primary: makeCell({ net_sentiment: 0.1 }),
          competitor: makeCell({ net_sentiment: 0.1 }),
          delta: 0,
          leader: "tie",
        }),
      ],
      primary_leads_count: 1,
      competitor_leads_count: 0,
      ties_count: 1,
    });
    const md = pairBriefToMarkdown({ pair, brief: makeBrief(), mentions: new Map() });
    expect(md).toContain("| Aspects led | 1 / 2 | 0 / 2 |");
    expect(md).toContain("| Aspects with data | 2 / 2 | 2 / 2 |");
    expect(md).toContain("| Avg net sentiment | +0.25 | -0.05 |");
    expect(md).toContain(`_Ties: 1 / 2 (net within ±${PAIR_LEAD_THRESHOLD.toFixed(2)})._`);
  });

  it("renders aspect comparison with em-dashes for missing cells (Δ is — when one side has no data)", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "thermals",
          primary: makeCell({ net_sentiment: 0.4 }),
          competitor: null,
          delta: 0.4,
          leader: "primary",
        }),
        makeRow({
          aspect: "battery",
          primary: makeCell({ net_sentiment: 0.2 }),
          competitor: makeCell({ net_sentiment: -0.1 }),
          delta: 0.3,
          leader: "primary",
        }),
      ],
    });
    const md = pairBriefToMarkdown({ pair, brief: makeBrief(), mentions: new Map() });
    // Missing-cell row: only primary has data → Δ collapses to —.
    expect(md).toContain("| Thermals | +0.40 | — | — |");
    // Both-sides row: sign reflects leader (primary → +, competitor → −).
    expect(md).toContain("| Battery | +0.20 | -0.10 | +0.30 |");
  });

  it("renders contrast paragraph with [n, m] cite refs", () => {
    const md = pairBriefToMarkdown({
      pair: makePair(),
      brief: makeBrief(),
      mentions: new Map(),
    });
    expect(md).toContain("## Contrast");
    expect(md).toMatch(/\*Alienware leans premium-build[^*]+\* \[1, 2, 3\]/);
  });

  it("renders 'Where X leads' bullets with cites and Δ formatted as +magnitude", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "build_quality",
          primary: makeCell({
            net_sentiment: 0.42,
            mention_ids: ["mp1", "mp2", "mp3"],
          }),
          competitor: makeCell({ net_sentiment: -0.18 }),
          delta: 0.6,
          leader: "primary",
        }),
        makeRow({
          aspect: "battery",
          primary: makeCell({ net_sentiment: -0.22 }),
          competitor: makeCell({
            net_sentiment: 0.14,
            mention_ids: ["mc1", "mc2"],
          }),
          delta: -0.36,
          leader: "competitor",
        }),
      ],
    });
    const md = pairBriefToMarkdown({ pair, brief: makeBrief(), mentions: new Map() });
    expect(md).toContain("## Where Alienware m18 R2 leads");
    expect(md).toMatch(/- \*\*Build\*\*: net \+0\.42 vs -0\.18 \(Δ \+0\.60\) \[\d, \d\]/);
    expect(md).toContain("## Where ROG Strix G18 leads");
    expect(md).toMatch(/- \*\*Battery\*\*: net -0\.22 vs \+0\.14 \(Δ \+0\.36\) \[\d, \d\]/);
  });

  it("emits an empty-state line when one side has no leaders above threshold", () => {
    const pair = makePair({
      rows: [
        makeRow({
          aspect: "thermals",
          primary: makeCell({ net_sentiment: 0.5, mention_ids: ["p1"] }),
          competitor: makeCell({ net_sentiment: -0.1 }),
          delta: 0.6,
          leader: "primary",
        }),
      ],
    });
    const md = pairBriefToMarkdown({ pair, brief: makeBrief(), mentions: new Map() });
    expect(md).toContain("_No aspects where ROG Strix G18 leads by more than 0.10._");
  });

  it("omits the Citations section when no mentions are cited", () => {
    const brief = makeBrief({
      narrative: ({
        brief_title: "x",
        contrast: { text: "no cites here.", cited_mention_ids: [] },
      } as unknown) as BriefView["narrative"],
    });
    const md = pairBriefToMarkdown({
      pair: makePair(),
      brief,
      mentions: new Map(),
    });
    expect(md).not.toContain("## Citations");
  });

  it("renders Citations with source · author · date when mentions resolve", () => {
    const md = pairBriefToMarkdown({
      pair: makePair(),
      brief: makeBrief(),
      mentions: new Map([
        ["m1", makeMention("m1", { source_type: "reddit_post", channel: "GamingLaptops", author: "alice" })],
        ["m2", makeMention("m2", { source_type: "article", channel: "Notebookcheck", author: null })],
        ["m3", makeMention("m3", { source_type: "youtube_chunk", channel: "Dave2D", author: "dave" })],
      ]),
    });
    expect(md).toContain("## Citations");
    expect(md).toContain("1. r/GamingLaptops · @alice");
    expect(md).toContain("2. Notebookcheck");
    expect(md).toContain("3. Dave2D · @dave");
  });
});
