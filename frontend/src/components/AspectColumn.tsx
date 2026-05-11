import { AspectRow as AspectRowAtom, ROW_GRID } from "@/components/atoms/AspectRow";
import type { AspectRow } from "@/lib/types";

/**
 * AspectColumn — one polarity scroller for the Standalone page.
 *
 * 3 stacked sub-sections (DESIGN_SYSTEM §5.1, locked session 16):
 *   Primary    — top-3 PRIMARY rows for this polarity, by total_mentions desc
 *   Secondary  — top-3 SECONDARY rows for this polarity, by total_mentions_secondary
 *                desc, excluding any aspect already in this column's Primary
 *   Long-tail  — every other aspect with any positive (or negative) bucket signal,
 *                excluding this column's Primary + Secondary
 *
 * Cross-scroller divergence: an aspect can appear in left-Primary AND
 * right-Secondary — same aspect, different rows, different metrics, different
 * tone chip. The chip on each row names the bucket the metrics belong to.
 *
 * Single outer scroll cap (`max-h-[320px] overflow-y-auto`) shows ~4–5
 * rows at a time and requires user scroll for the rest — anchors the
 * BriefPanel below at a stable y. Sub-headers are sticky to the scroll
 * viewport so the active sub-section is always identified. Chevron is
 * visual only — non-collapsible v1.
 */

export type Polarity = "positive" | "negative";
export type Bucket = "primary" | "secondary";

export interface PartitionedColumn {
  primary: AspectRow[];
  secondary: AspectRow[];
  longTail: Array<{ row: AspectRow; bucket: Bucket }>;
}

const TOP_N = 3;

function hasPrimarySignal(row: AspectRow, polarity: Polarity): boolean {
  if (row.total_mentions <= 0) return false;
  return polarity === "positive" ? row.net_sentiment >= 0 : row.net_sentiment < 0;
}

function hasSecondarySignal(row: AspectRow, polarity: Polarity): boolean {
  if (row.total_mentions_secondary <= 0) return false;
  return polarity === "positive"
    ? row.net_sentiment_secondary >= 0
    : row.net_sentiment_secondary < 0;
}

export function partitionAspects(
  aspects: AspectRow[],
  polarity: Polarity,
): PartitionedColumn {
  const primary = aspects
    .filter((r) => hasPrimarySignal(r, polarity))
    .sort((a, b) => b.total_mentions - a.total_mentions)
    .slice(0, TOP_N);

  const primaryNames = new Set(primary.map((r) => r.aspect));

  const secondary = aspects
    .filter((r) => hasSecondarySignal(r, polarity))
    .filter((r) => !primaryNames.has(r.aspect))
    .sort((a, b) => b.total_mentions_secondary - a.total_mentions_secondary)
    .slice(0, TOP_N);

  const secondaryNames = new Set(secondary.map((r) => r.aspect));

  const longTail: Array<{ row: AspectRow; bucket: Bucket }> = aspects
    .filter((r) => !primaryNames.has(r.aspect) && !secondaryNames.has(r.aspect))
    .filter((r) => hasPrimarySignal(r, polarity) || hasSecondarySignal(r, polarity))
    .map((r) => ({
      row: r,
      bucket: hasPrimarySignal(r, polarity) ? ("primary" as const) : ("secondary" as const),
    }))
    .sort((a, b) => {
      const aSize = Math.max(a.row.total_mentions, a.row.total_mentions_secondary);
      const bSize = Math.max(b.row.total_mentions, b.row.total_mentions_secondary);
      return bSize - aSize;
    });

  return { primary, secondary, longTail };
}

function SubHeader({ label }: { label: string }): JSX.Element {
  return (
    <div className="sticky top-[28px] z-10 flex items-center gap-1.5 border-b border-border bg-surface-alt px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
      <span aria-hidden className="text-fg-muted">▾</span>
      <span>{label}</span>
    </div>
  );
}

interface EmptySubProps {
  message: string;
}

function EmptySub({ message }: EmptySubProps): JSX.Element {
  return <p className="px-4 py-3 text-xs italic text-fg-muted">{message}</p>;
}

export interface AspectColumnProps {
  title: string;
  polarity: Polarity;
  rows: AspectRow[];
  onRowClick: (row: AspectRow, bucket: Bucket) => void;
}

export function AspectColumn({
  title,
  polarity,
  rows,
  onRowClick,
}: AspectColumnProps): JSX.Element {
  const { primary, secondary, longTail } = partitionAspects(rows, polarity);

  const polarityLabel =
    polarity === "positive" ? "positive net sentiment" : "negative net sentiment";

  return (
    <div className="flex flex-col rounded-md border border-border bg-surface shadow-card">
      <div className="flex items-center justify-between border-b border-border bg-surface-alt px-4 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          {title}
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-fg-muted">
          {polarityLabel}
        </span>
      </div>

      <div className="max-h-[320px] overflow-y-auto">
        <div
          className={`sticky top-0 z-20 grid ${ROW_GRID} items-center gap-3 border-b border-border bg-surface px-4 py-1.5 text-[10px] font-medium uppercase tracking-wide text-fg-muted`}
        >
          <span>aspect</span>
          <span className="text-center" title="net sentiment, −1 to +1">sentiment</span>
          <span
            className="text-right"
            title="% of mentions from verified-purchase reviewers"
          >
            verified
          </span>
          <span className="text-right" title="total mentions for this aspect">
            mentions
          </span>
        </div>

        <SubHeader label="Primary signal" />
        {primary.length === 0 ? (
          <EmptySub message="No primary aspects in this polarity" />
        ) : (
          <ul className="flex flex-col">
            {primary.map((row) => (
              <li key={`pri-${row.aspect}`} className="border-b border-border last:border-b-0">
                <AspectRowAtom row={row} bucket="primary" onClick={onRowClick} />
              </li>
            ))}
          </ul>
        )}

        <SubHeader label="Secondary signal" />
        {secondary.length === 0 ? (
          <EmptySub message="No secondary aspects in this polarity" />
        ) : (
          <ul className="flex flex-col">
            {secondary.map((row) => (
              <li key={`sec-${row.aspect}`} className="border-b border-border last:border-b-0">
                <AspectRowAtom row={row} bucket="secondary" onClick={onRowClick} />
              </li>
            ))}
          </ul>
        )}

        <SubHeader label="Long-tail" />
        {longTail.length === 0 ? (
          <EmptySub message="No long-tail aspects in this polarity" />
        ) : (
          <ul className="flex flex-col">
            {longTail.map(({ row, bucket }) => (
              <li key={`tail-${row.aspect}`} className="border-b border-border last:border-b-0">
                <AspectRowAtom row={row} bucket={bucket} onClick={onRowClick} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
