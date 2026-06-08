import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VerbatimCard } from "./VerbatimCard";
import type { AspectTag, MentionView } from "@/lib/types";

function makeMention(
  aspectTags: AspectTag[],
  overrides: Partial<MentionView> = {},
): MentionView {
  return {
    mention_id: "m1",
    source_type: "article",
    channel: "Notebookcheck",
    author: "Allen Ngo",
    published_at: "2026-04-21",
    raw_text: "Pushing performance boundaries with the Arrow Lake chip.",
    url: "https://example.com",
    verified: false,
    upvotes: null,
    rating: null,
    aspect_tags: aspectTags,
    tombstoned_at: null,
    tombstone_reason: null,
    ...overrides,
  };
}

// A multi-aspect mention whose FIRST tag is performance-positive but which also
// carries a thermals-negative tag — the exact shape that made the heatmap look
// contradictory (negative thermals cell, positive-looking card).
const MULTI: AspectTag[] = [
  { aspect: "performance", polarity: "positive", intensity: "high", product_id: "aw16" },
  { aspect: "thermals", polarity: "negative", intensity: "medium", product_id: "aw16" },
];

describe("VerbatimCard focus aspect", () => {
  it("shows the focus aspect's tag, not the arbitrary first tag", () => {
    render(<VerbatimCard mention={makeMention(MULTI)} focusAspect="thermals" />);
    expect(screen.getByText("thermals · negative")).toBeInTheDocument();
    expect(screen.queryByText("performance · positive")).not.toBeInTheDocument();
  });

  it("falls back to the first tag when no focus aspect is given (pooled context)", () => {
    render(<VerbatimCard mention={makeMention(MULTI)} />);
    expect(screen.getByText("performance · positive")).toBeInTheDocument();
    expect(screen.queryByText("thermals · negative")).not.toBeInTheDocument();
  });

  it("disambiguates by product when a mention tags the same aspect twice", () => {
    const dualProduct: AspectTag[] = [
      { aspect: "thermals", polarity: "positive", intensity: "low", product_id: "competitor" },
      { aspect: "thermals", polarity: "negative", intensity: "high", product_id: "aw16" },
    ];
    render(
      <VerbatimCard
        mention={makeMention(dualProduct)}
        focusAspect="thermals"
        focusProductId="aw16"
      />,
    );
    expect(screen.getByText("thermals · negative")).toBeInTheDocument();
    expect(screen.queryByText("thermals · positive")).not.toBeInTheDocument();
  });

  it("omits the chip rather than mislabel when the focus aspect has no tag", () => {
    render(<VerbatimCard mention={makeMention(MULTI)} focusAspect="battery" />);
    expect(screen.queryByText(/· (positive|negative|neutral)/)).not.toBeInTheDocument();
  });
});
