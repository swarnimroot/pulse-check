import { useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MentionView } from "@/lib/types";
import { VerbatimCard } from "@/components/atoms";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * CitationPanel — narrow right-side panel (380px) for a single claim's
 * cited mentions. No filters.
 *
 * Co-existence rule: if EvidenceDrawer is also open (440px), this panel
 * offsets to `right: 440px` so both are visible simultaneously.
 */

export interface CitationPanelProps {
  open: boolean;
  claimText: string;
  mentions: MentionView[];
  offsetForDrawer?: boolean;
  onClose: () => void;
  // See EvidenceDrawer — same optimistic-open pattern when Standalone fetches
  // /api/mentions in response to a CiteChip click.
  loading?: boolean;
  errorMessage?: string | null;
}

export function CitationPanel({
  open,
  claimText,
  mentions,
  offsetForDrawer = false,
  onClose,
  loading = false,
  errorMessage = null,
}: CitationPanelProps): JSX.Element | null {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <aside
      role="complementary"
      aria-label="Citation detail"
      style={{ right: offsetForDrawer ? 440 : 0 }}
      className={cn(
        "fixed inset-y-0 z-20 flex w-[380px] flex-col border-l border-border bg-surface shadow-card",
        "transition-[right] duration-2 ease-aw",
      )}
    >
      <header className="shrink-0 border-b border-border px-4 pt-3 pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
              Cited mentions
            </span>
            <p className="text-sm leading-snug text-fg">“{claimText}”</p>
            <span className="text-xs text-fg-secondary">{mentions.length} cited</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-fg-muted hover:bg-surface-alt hover:text-fg"
            aria-label="close citation panel"
          >
            <X size={16} />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-surface-alt p-4">
        {loading ? (
          <div
            className="flex flex-col gap-3"
            aria-label="Loading citations"
          >
            {Array.from({ length: 3 }).map((_, idx) => (
              <div
                key={idx}
                className="flex flex-col gap-2 rounded-md border border-border bg-surface p-3"
              >
                <Skeleton className="h-3 w-1/4" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            ))}
          </div>
        ) : errorMessage !== null ? (
          <p className="py-8 text-center text-xs text-danger">
            Couldn't load citations: {errorMessage}
          </p>
        ) : mentions.length === 0 ? (
          <p className="py-8 text-center text-xs text-fg-muted">
            no cited mentions resolved.
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {mentions.map((m) => (
              <VerbatimCard key={m.mention_id} mention={m} />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
