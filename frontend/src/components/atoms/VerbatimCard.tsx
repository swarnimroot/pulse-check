import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MentionView, Polarity, Intensity } from "@/lib/types";
import { Chip, type ChipTone } from "./Chip";
import { SourceMark, sourceLabel } from "./SourceMark";

/**
 * VerbatimCard — quote card for the EvidenceDrawer / CitationPanel.
 *
 * Section order per DESIGN_SYSTEM §3.8:
 *   1. SourceMark + source label + channel + url-out icon (top-right)
 *   2. Posted date · author (muted, 11px)
 *   3. Quote in left-bordered blockquote, 13px / 1.5; truncate at 180 chars
 *      with show-more / show-less
 *   4. Tag row 1: aspect-polarity chip + intensity chip
 *   5. Tag row 2 (only if data exists): verified, ↑ upvotes, ★ rating,
 *      link-dead marker (when `tombstoned_at` is set — session-38 lift of
 *      the session-13 lock; ownership phrase still suppressed).
 */

const POLARITY_TONE: Record<Polarity, ChipTone> = {
  positive: "pos",
  negative: "neg",
  neutral: "neu",
};
const INTENSITY_TONE: Record<Intensity, ChipTone> = {
  high: "high",
  medium: "med",
  low: "low",
};

const TRUNCATE_AT = 180;

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return DATE_FMT.format(d);
}

export interface VerbatimCardProps {
  mention: MentionView;
  className?: string;
  // Aspect-scoped drill context (heatmap cell / Standalone aspect / Pair cell).
  // When set, the card shows the tag for THIS aspect — the lens the mention
  // entered the list through — instead of an arbitrary first tag, so the chip's
  // polarity matches the cell color the operator clicked. `focusProductId`
  // further disambiguates when a mention carries the same aspect for more than
  // one product. Omitted in pooled contexts (CitationPanel / Showcase), where
  // the card falls back to the (now canonically-ordered) first tag.
  focusAspect?: string;
  focusProductId?: string;
}

export function VerbatimCard({
  mention,
  className,
  focusAspect,
  focusProductId,
}: VerbatimCardProps): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const needsTruncate = mention.raw_text.length > TRUNCATE_AT;
  const quote = expanded || !needsTruncate
    ? mention.raw_text
    : `${mention.raw_text.slice(0, TRUNCATE_AT)}…`;

  // No focus → pooled context, show the first (canonically-ordered) tag. With a
  // focus aspect, show that aspect's tag and never fall back to an unrelated
  // one: an absent match means the mention shouldn't be in this list at all
  // (guarded by the aggregation↔drawer regression test), so omit the chip
  // rather than mislabel the quote.
  const primaryTag =
    focusAspect === undefined
      ? mention.aspect_tags[0]
      : mention.aspect_tags.find(
          (t) =>
            t.aspect === focusAspect &&
            (focusProductId === undefined || t.product_id === focusProductId),
        );

  const showTagRow2 =
    mention.verified ||
    typeof mention.upvotes === "number" ||
    typeof mention.rating === "number" ||
    mention.tombstoned_at !== null;

  return (
    <article
      className={cn(
        "flex flex-col gap-2 rounded-md border border-border bg-surface p-3 shadow-card",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-fg-secondary">
          <SourceMark source={mention.source_type} />
          <span className="font-medium text-fg">{sourceLabel(mention.source_type)}</span>
          {mention.channel && (
            <>
              <span className="text-fg-muted">·</span>
              <span>{mention.channel}</span>
            </>
          )}
        </div>
        <a
          href={mention.url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-fg-muted transition-colors duration-1 ease-aw hover:text-accent"
          aria-label="open source"
        >
          <ExternalLink size={12} />
        </a>
      </header>

      <div className="text-[11px] text-fg-muted">
        {formatDate(mention.published_at)}
        {mention.author && (
          <>
            {" · "}
            <span>{mention.author}</span>
          </>
        )}
      </div>

      <blockquote className="border-l-2 border-border-strong pl-3 text-[13px] leading-[1.5] text-fg-secondary">
        “{quote}”
        {needsTruncate && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="ml-2 text-[11px] font-medium text-accent hover:text-accent-hover"
          >
            {expanded ? "show less" : "show more"}
          </button>
        )}
      </blockquote>

      {primaryTag && (
        <div className="flex flex-wrap items-center gap-1">
          <Chip tone={POLARITY_TONE[primaryTag.polarity]}>
            {primaryTag.aspect} · {primaryTag.polarity}
          </Chip>
          <Chip tone={INTENSITY_TONE[primaryTag.intensity]}>{primaryTag.intensity}</Chip>
        </div>
      )}

      {showTagRow2 && (
        <div className="flex flex-wrap items-center gap-1">
          {mention.verified && <Chip tone="verified">verified purchase</Chip>}
          {typeof mention.upvotes === "number" && (
            <Chip tone="meta">↑ {mention.upvotes}</Chip>
          )}
          {typeof mention.rating === "number" && (
            <Chip tone="meta">★ {mention.rating.toFixed(1)}</Chip>
          )}
          {mention.tombstoned_at !== null && (
            <Chip tone="tombstone">link dead</Chip>
          )}
        </div>
      )}
    </article>
  );
}
