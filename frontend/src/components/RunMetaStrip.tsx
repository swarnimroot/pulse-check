import { cn } from "@/lib/utils";

/**
 * RunMetaStrip — thin provenance band atop Standalone / Compare pages.
 *
 * Locked label format per session-13:
 *   "1,143 mentions · 6-month window · last refreshed 2026-05-07"
 *
 * Excluded by design: run_id, taxonomy version, generated-by-pipeline metadata.
 */

const NUMBER_FMT = new Intl.NumberFormat("en-US");
const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatRefreshed(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return DATE_FMT.format(d);
}

export interface RunMetaStripProps {
  totalMentions: number;
  windowLabel: string;
  lastRefreshed: string;
  className?: string;
}

export function RunMetaStrip({
  totalMentions,
  windowLabel,
  lastRefreshed,
  className,
}: RunMetaStripProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex h-7 items-center gap-3 border-b border-border bg-surface-alt px-6 text-[11px] text-fg-muted",
        className,
      )}
    >
      <span className="tabular text-fg">
        {NUMBER_FMT.format(totalMentions)} mentions
      </span>
      <span className="text-fg-muted">·</span>
      <span>{windowLabel}</span>
      <span className="text-fg-muted">·</span>
      <span>last refreshed {formatRefreshed(lastRefreshed)}</span>
    </div>
  );
}
