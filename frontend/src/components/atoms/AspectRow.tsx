import { Chip } from "./Chip";
import type { ChipTone } from "./Chip";
import type { AspectRow as AspectRowType } from "@/lib/types";

/**
 * AspectRow — single row in an AspectColumn sub-section.
 *
 * Renders the metrics of the named bucket (PRIMARY or SECONDARY), with a
 * small bucket chip inline next to the aspect name. Single-line at-rest
 * layout per DESIGN_SYSTEM §5.1: aspect (with bucket chip) · sentiment ·
 * verified · mentions.
 */

export const ROW_GRID = "grid-cols-[minmax(0,1fr)_72px_72px_72px]";

export type AspectRowBucket = "primary" | "secondary";

export interface AspectRowProps {
  row: AspectRowType;
  bucket: AspectRowBucket;
  onClick: (row: AspectRowType, bucket: AspectRowBucket) => void;
}

interface BucketMetrics {
  totalMentions: number;
  netSentiment: number;
  verifiedPct: number;
}

function pickMetrics(row: AspectRowType, bucket: AspectRowBucket): BucketMetrics {
  if (bucket === "primary") {
    return {
      totalMentions: row.total_mentions,
      netSentiment: row.net_sentiment,
      verifiedPct: row.verified_pct,
    };
  }
  return {
    totalMentions: row.total_mentions_secondary,
    netSentiment: row.net_sentiment_secondary,
    verifiedPct: row.verified_pct_secondary,
  };
}

function sentimentTone(net: number): ChipTone {
  if (net > 0.15) return "pos";
  if (net < -0.15) return "neg";
  return "neu";
}

export function AspectRow({ row, bucket, onClick }: AspectRowProps): JSX.Element {
  const m = pickMetrics(row, bucket);
  const tone = sentimentTone(m.netSentiment);
  const sign = m.netSentiment >= 0 ? "+" : "";

  return (
    <button
      type="button"
      onClick={() => onClick(row, bucket)}
      title={`open evidence for ${row.aspect} (${bucket})`}
      className={`grid ${ROW_GRID} w-full cursor-zoom-in items-center gap-3 bg-transparent px-4 py-3 text-left transition-colors duration-1 ease-aw hover:bg-surface-alt`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-medium text-fg">{row.aspect}</span>
        <Chip tone={bucket}>{bucket}</Chip>
      </span>
      <span className="flex justify-center">
        <Chip tone={tone}>
          {sign}
          {m.netSentiment.toFixed(2)}
        </Chip>
      </span>
      <span className="tabular text-right text-xs text-fg-secondary">
        {m.verifiedPct.toFixed(0)}%
      </span>
      <span className="tabular text-right text-sm text-fg-secondary">{m.totalMentions}</span>
    </button>
  );
}
