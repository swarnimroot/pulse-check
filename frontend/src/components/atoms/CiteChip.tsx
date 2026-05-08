import { cn } from "@/lib/utils";

/**
 * CiteChip — per-claim citation marker (replaces prototype `[n]` numbering).
 *
 * Backend already attaches `cited_mention_ids` to each Claim, so we render
 * a chip per claim with the count instead of a numbered marker tied to a
 * separate citation_map. Hover preview tooltip; click opens the
 * CitationPanel pinned right (CitationPanel offsets when EvidenceDrawer
 * is also open).
 */

export interface CiteChipProps {
  count: number;
  citedMentionIds: string[];
  onClick?: (citedMentionIds: string[]) => void;
  previewText?: string;
  className?: string;
}

export function CiteChip({
  count,
  citedMentionIds,
  onClick,
  previewText,
  className,
}: CiteChipProps): JSX.Element {
  const label = `${count} mention${count === 1 ? "" : "s"}`;
  const tooltip = previewText ?? `${label} cited`;
  return (
    <button
      type="button"
      onClick={onClick ? () => onClick(citedMentionIds) : undefined}
      title={tooltip}
      className={cn(
        "ml-1 inline-flex h-[18px] items-center rounded-sm bg-accent-soft px-1.5 text-[11px] font-medium leading-none text-accent-hover",
        "transition-colors duration-1 ease-aw",
        "hover:bg-accent hover:text-fg-on-accent",
        className,
      )}
    >
      {label}
    </button>
  );
}
