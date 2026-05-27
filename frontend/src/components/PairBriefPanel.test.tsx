import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PairBriefPanel } from "./PairBriefPanel";
import type { PairBriefNarrative } from "@/lib/types";

function makeNarrative(
  overrides: Partial<PairBriefNarrative> = {},
): PairBriefNarrative {
  return {
    brief_title: "Alienware 16 Aurora vs ROG Strix G16",
    contrast: {
      text: "The Alienware leads on build and thermals. The ROG counters on display and gaming throughput.",
      cited_mention_ids: ["mp1", "mc1"],
    },
    ...overrides,
  };
}

describe("PairBriefPanel rendering", () => {
  it("renders the title + contrast paragraph", () => {
    render(<PairBriefPanel narrative={makeNarrative()} onCite={() => {}} />);

    expect(
      screen.getByText("Alienware 16 Aurora vs ROG Strix G16"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The Alienware leads on build and thermals/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Pair brief contrast")).toBeInTheDocument();
  });

  it("invokes onCite with the contrast text + cited mention IDs", () => {
    const onCite = vi.fn();
    const narrative = makeNarrative();
    render(<PairBriefPanel narrative={narrative} onCite={onCite} />);

    const chip = screen.getByTitle("2 mentions cited");
    fireEvent.click(chip);
    expect(onCite).toHaveBeenCalledWith(narrative.contrast.text, ["mp1", "mc1"]);
  });

  it("renders without a cite chip when cited_mention_ids is empty", () => {
    render(
      <PairBriefPanel
        narrative={makeNarrative({
          contrast: {
            text: "Insufficient signal on either side to draw a meaningful contrast.",
            cited_mention_ids: [],
          },
        })}
        onCite={() => {}}
      />,
    );

    expect(
      screen.getByText(/Insufficient signal on either side/),
    ).toBeInTheDocument();
    expect(screen.queryByTitle(/mentions cited/)).not.toBeInTheDocument();
  });

  it("displays model + promptVersion in the header when provided", () => {
    render(
      <PairBriefPanel
        narrative={makeNarrative()}
        model="claude-sonnet-4-6"
        promptVersion="pair_brief_v1"
        onCite={() => {}}
      />,
    );

    expect(
      screen.getByText(/claude-sonnet-4-6/),
    ).toBeInTheDocument();
    expect(screen.getByText(/pair_brief_v1/)).toBeInTheDocument();
  });
});
