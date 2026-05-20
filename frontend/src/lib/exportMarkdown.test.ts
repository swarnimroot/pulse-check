import { describe, expect, it } from "vitest";
import { briefToMarkdown } from "./exportMarkdown";
import type {
  AspectRow,
  BriefView,
  Claim,
  MentionView,
  ProductDetail,
} from "@/lib/types";

function makeAspectRow(overrides: Partial<AspectRow> = {}): AspectRow {
  return {
    aspect: "thermals",
    total_mentions: 0,
    net_sentiment: 0,
    intensity_counts: {},
    verified_pct: 0,
    sources: [],
    mention_ids: [],
    total_mentions_secondary: 0,
    net_sentiment_secondary: 0,
    intensity_counts_secondary: {},
    verified_pct_secondary: 0,
    sources_secondary: [],
    mention_ids_secondary: [],
    ...overrides,
  };
}

function makeProduct(overrides: Partial<ProductDetail> = {}): ProductDetail {
  return {
    product_id: "msi_cyborg_15",
    display_name: "MSI Cyborg 15",
    brand: "MSI",
    aliases: [],
    aspects: [
      makeAspectRow({ aspect: "thermals", total_mentions: 24, net_sentiment: -0.5 }),
      makeAspectRow({ aspect: "performance", total_mentions: 18, net_sentiment: 0.3 }),
    ],
    run_meta: {
      total_mentions: 120,
      window_label: "Last 90 days",
      last_refreshed: "2026-05-20T12:00:00Z",
    },
    latest_brief_id: 42,
    ...overrides,
  };
}

function makeBrief(overrides: Partial<BriefView> = {}): BriefView {
  return {
    brief_id: 42,
    run_id: "run_wave5_v1",
    scope_type: "ASPECT_1_SKU",
    scope_id: "msi_cyborg_15",
    prompt_version: "a1_brief_v2",
    model: "claude-sonnet-4-6",
    generated_at: "2026-05-20T12:00:00Z",
    narrative: { brief_title: "MSI Cyborg 15", sections: [] },
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

describe("briefToMarkdown", () => {
  it("renders the H1 heading + italic brand/mentions/window line + run id", () => {
    const md = briefToMarkdown({
      product: makeProduct(),
      brief: makeBrief(),
      strengths: [],
      weaknesses: [],
      citedIds: [],
      citeNumber: new Map(),
      mentions: new Map(),
    });
    expect(md).toContain("# MSI Cyborg 15");
    expect(md).toContain("*MSI · 120 public mentions analyzed · Last 90 days*");
    expect(md).toContain("Run: `run_wave5_v1`");
  });

  it("renders all 11 canonical aspects with em-dash + 0 for no-data rows", () => {
    const md = briefToMarkdown({
      product: makeProduct({
        aspects: [
          makeAspectRow({ aspect: "thermals", total_mentions: 24, net_sentiment: -0.4 }),
        ],
      }),
      brief: makeBrief(),
      strengths: [],
      weaknesses: [],
      citedIds: [],
      citeNumber: new Map(),
      mentions: new Map(),
    });
    expect(md).toContain("| Thermals | -0.40 | 24 |");
    expect(md).toContain("| Performance | — | 0 |");
    expect(md).toContain("| Aesthetics | — | 0 |");
    const expectedLabels = [
      "Thermals",
      "Performance",
      "Keyboard",
      "Display",
      "Battery",
      "Build",
      "Software",
      "Price",
      "Support",
      "Aesthetics",
      "Portability",
    ];
    for (const label of expectedLabels) {
      expect(md).toContain(`| ${label} |`);
    }
  });

  it("renders strengths with [n, m] citation refs from the citeNumber map", () => {
    const strengths: Claim[] = [
      {
        header: "Strong keyboard",
        claim_text: "Owners praise the typing feel.",
        cited_mention_ids: ["m1", "m2"],
      },
    ];
    const md = briefToMarkdown({
      product: makeProduct(),
      brief: makeBrief(),
      strengths,
      weaknesses: [],
      citedIds: ["m1", "m2"],
      citeNumber: new Map([
        ["m1", 1],
        ["m2", 2],
      ]),
      mentions: new Map([
        ["m1", makeMention("m1")],
        ["m2", makeMention("m2")],
      ]),
    });
    expect(md).toContain("- Strong keyboard [1, 2]");
  });

  it("renders the empty-strengths and empty-complaints fallbacks", () => {
    const md = briefToMarkdown({
      product: makeProduct(),
      brief: makeBrief(),
      strengths: [],
      weaknesses: [],
      citedIds: [],
      citeNumber: new Map(),
      mentions: new Map(),
    });
    expect(md).toContain("_No high-signal strengths in this brief._");
    expect(md).toContain("_No high-signal complaints in this brief._");
  });

  it("omits the Citations section when citedIds is empty, includes it otherwise", () => {
    const empty = briefToMarkdown({
      product: makeProduct(),
      brief: makeBrief(),
      strengths: [],
      weaknesses: [],
      citedIds: [],
      citeNumber: new Map(),
      mentions: new Map(),
    });
    expect(empty).not.toContain("## Citations");

    const withCites = briefToMarkdown({
      product: makeProduct(),
      brief: makeBrief(),
      strengths: [],
      weaknesses: [],
      citedIds: ["m1"],
      citeNumber: new Map([["m1", 1]]),
      mentions: new Map([["m1", makeMention("m1", { source_type: "reddit_post", channel: "GamingLaptops" })]]),
    });
    expect(withCites).toContain("## Citations");
    expect(withCites).toContain("1. r/GamingLaptops");
  });
});
