import { cn } from "@/lib/utils";

/**
 * IntensityBar — horizontal stacked bar (high / med / low).
 *
 * Per DESIGN_SYSTEM §3.5: 100–120px wide; high #C13030, med #B8860B,
 * low #D9DCE7 (the border colour, used as the dim segment). Tooltip
 * surfaces raw counts.
 */

export interface IntensityCounts {
  high?: number;
  medium?: number;
  low?: number;
}

export interface IntensityBarProps {
  intensityCounts: IntensityCounts;
  width?: number;
  className?: string;
}

export function IntensityBar({
  intensityCounts,
  width = 110,
  className,
}: IntensityBarProps): JSX.Element {
  const high = intensityCounts.high ?? 0;
  const med = intensityCounts.medium ?? 0;
  const low = intensityCounts.low ?? 0;
  const total = high + med + low;
  const pct = (n: number): string => (total === 0 ? "0%" : `${(n / total) * 100}%`);
  const tooltip = `high ${high} · med ${med} · low ${low}`;
  return (
    <span
      className={cn("inline-flex h-2 overflow-hidden rounded-sm bg-border", className)}
      style={{ width }}
      title={tooltip}
      aria-label={tooltip}
    >
      {high > 0 && <span style={{ width: pct(high), backgroundColor: "#C13030" }} />}
      {med > 0 && <span style={{ width: pct(med), backgroundColor: "#B8860B" }} />}
      {low > 0 && <span style={{ width: pct(low), backgroundColor: "#D9DCE7" }} />}
    </span>
  );
}
