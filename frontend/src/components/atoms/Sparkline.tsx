import { cn } from "@/lib/utils";

/**
 * Sparkline — recency volume polyline.
 *
 * Per DESIGN_SYSTEM §3.6: 1.5px stroke, accent colour, 120×24 typical.
 * 11.2 renders fixture data; 11.3 will derive 26-week series at API time
 * from `mentions.published_at` for the aspect's mention_ids (open backend
 * dependency — `aggregates_aspect_sku.by_recency` carries coarser buckets).
 */

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({
  data,
  width = 120,
  height = 24,
  className,
}: SparklineProps): JSX.Element {
  if (data.length === 0) {
    return (
      <svg
        width={width}
        height={height}
        className={cn("inline-block", className)}
        aria-label="no recency data"
      />
    );
  }
  const max = Math.max(...data, 1);
  const stepX = data.length === 1 ? 0 : width / (data.length - 1);
  const points = data
    .map((v, i) => `${i * stepX},${height - (v / max) * height}`)
    .join(" ");
  return (
    <svg
      width={width}
      height={height}
      className={cn("inline-block", className)}
      aria-label={`recency series, ${data.length} buckets`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--aw-accent)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
