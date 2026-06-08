import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { EvidenceDrawer } from "./EvidenceDrawer";
import type { AspectTag, MentionView } from "@/lib/types";

function makeMention(
  id: string,
  aspectTags: AspectTag[],
  overrides: Partial<MentionView> = {},
): MentionView {
  return {
    mention_id: id,
    source_type: "article",
    channel: "Notebookcheck",
    author: "Allen Ngo",
    published_at: "2026-04-21",
    raw_text: `verdict ${id}`,
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

// thermals-negative mention whose first tag is performance-positive.
const MULTI: AspectTag[] = [
  { aspect: "performance", polarity: "positive", intensity: "high", product_id: "aw16" },
  { aspect: "thermals", polarity: "negative", intensity: "medium", product_id: "aw16" },
];

describe("EvidenceDrawer aspect-scoped drill", () => {
  it("renders each card's chip for the drilled aspect (header matches chip)", () => {
    render(
      <EvidenceDrawer
        open
        aspect="thermals"
        productName="Alienware 16 Area-51"
        productId="aw16"
        mentions={[makeMention("m1", MULTI)]}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/· thermals$/)).toBeInTheDocument(); // header
    expect(screen.getByText("thermals · negative")).toBeInTheDocument(); // chip
    expect(screen.queryByText("performance · positive")).not.toBeInTheDocument();
  });

  it("scopes the intensity filter to the drilled aspect", () => {
    // thermals is low-intensity; performance is high. Filtering 'high' must drop
    // this mention — the high tag belongs to a different aspect.
    const tags: AspectTag[] = [
      { aspect: "performance", polarity: "positive", intensity: "high", product_id: "aw16" },
      { aspect: "thermals", polarity: "negative", intensity: "low", product_id: "aw16" },
    ];
    render(
      <EvidenceDrawer
        open
        aspect="thermals"
        productName="Alienware 16 Area-51"
        productId="aw16"
        mentions={[makeMention("m1", tags)]}
        onClose={() => {}}
      />,
    );
    // Selects in DOM order: [0] source, [1] intensity, [2] recency (disabled).
    const intensitySelect = screen.getAllByRole("combobox")[1];
    fireEvent.change(intensitySelect, { target: { value: "high" } });
    expect(screen.getByText(/no mentions match these filters/)).toBeInTheDocument();
  });
});
