import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { BriefPanel } from "./BriefPanel";
import type { BriefNarrative } from "@/lib/types";

function makeNarrative(
  overrides: Partial<BriefNarrative> = {},
): BriefNarrative {
  return {
    brief_title: "Test Product — A1 voice",
    sections: [
      {
        heading: "High-confidence strengths",
        claims: [
          {
            header: "Performance impresses",
            claim_text: "Owners praise the responsiveness under load.",
            cited_mention_ids: ["m1", "m2"],
          },
        ],
      },
      {
        heading: "High-confidence weaknesses",
        claims: [
          {
            header: "Thermals run hot",
            claim_text: "Sustained gaming surfaces heat complaints.",
            cited_mention_ids: ["m3"],
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe("BriefPanel summary rendering", () => {
  it("renders the summary paragraph when narrative.summary is present", () => {
    const narrative = makeNarrative({
      summary: {
        text: "Discussion clusters around heat and build. Broad consensus on chassis quality; opinions split on cooling.",
        cited_mention_ids: ["m1", "m2"],
      },
    });

    render(<BriefPanel narrative={narrative} onCite={() => {}} />);

    expect(screen.getByText(/Discussion clusters around heat/)).toBeInTheDocument();
    expect(screen.getByLabelText("Brief summary")).toBeInTheDocument();
  });

  it("does not render the summary block when narrative.summary is null", () => {
    const narrative = makeNarrative({ summary: null });

    render(<BriefPanel narrative={narrative} onCite={() => {}} />);

    expect(screen.queryByLabelText("Brief summary")).not.toBeInTheDocument();
  });

  it("summary cite chip click invokes onCite with the cited mention IDs", () => {
    const onCite = vi.fn();
    const narrative = makeNarrative({
      summary: {
        text: "Discussion clusters around heat and build.",
        cited_mention_ids: ["m1", "m2"],
      },
    });

    render(<BriefPanel narrative={narrative} onCite={onCite} />);

    // CiteChip renders a button labeled "N mentions". The summary + section
    // claims each get their own chip; "2 mentions" is unique to the summary
    // (claims here cite 2 and 1 IDs respectively). Disambiguate by title.
    const summaryChip = screen.getAllByTitle("2 mentions cited")[0];
    fireEvent.click(summaryChip);
    expect(onCite).toHaveBeenCalledWith(
      "Discussion clusters around heat and build.",
      ["m1", "m2"],
    );
  });

  it("renders existing strengths and weaknesses unchanged when summary is null", () => {
    const narrative = makeNarrative({ summary: null });

    render(<BriefPanel narrative={narrative} onCite={() => {}} />);

    expect(screen.getByText("Performance impresses")).toBeInTheDocument();
    expect(screen.getByText("Thermals run hot")).toBeInTheDocument();
  });
});
