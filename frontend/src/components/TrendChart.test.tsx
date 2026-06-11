import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrendChart } from "./TrendChart";
import type { TrendBucket } from "@/lib/trendRollup";

const BUCKETS: TrendBucket[] = [
  { label: "Jun '26", net: 0.75, vol: 40 },
  { label: "Jul '26", net: -0.4, vol: 5 },
];

describe("TrendChart", () => {
  it("renders an empty svg with a no-data label when there are no buckets", () => {
    render(<TrendChart buckets={[]} />);
    expect(screen.getByLabelText("no trend data")).toBeInTheDocument();
  });

  it("labels the svg with the point count", () => {
    render(<TrendChart buckets={BUCKETS} />);
    expect(screen.getByLabelText("trend, 2 points")).toBeInTheDocument();
  });

  it("renders per-point sentiment value labels and x-axis labels", () => {
    render(<TrendChart buckets={BUCKETS} />);
    expect(screen.getByText("+0.75")).toBeInTheDocument();
    expect(screen.getByText("−0.40")).toBeInTheDocument();
    expect(screen.getByText("Jun '26")).toBeInTheDocument();
    expect(screen.getByText("Jul '26")).toBeInTheDocument();
  });

  it("hides per-point value labels when the bucket count is dense (>18)", () => {
    const many: TrendBucket[] = Array.from({ length: 20 }, (_, i) => ({
      label: `w${i + 1}`,
      net: 0.5,
      vol: 10,
    }));
    render(<TrendChart buckets={many} />);
    // 20 points all net=+0.50 — labels suppressed, so none render.
    expect(screen.queryByText("+0.50")).not.toBeInTheDocument();
    expect(screen.getByLabelText("trend, 20 points")).toBeInTheDocument();
  });
});
