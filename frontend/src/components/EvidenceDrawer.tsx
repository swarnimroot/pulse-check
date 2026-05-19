import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MentionView, Intensity } from "@/lib/types";
import { VerbatimCard } from "@/components/atoms";

/**
 * EvidenceDrawer — persistent right-side overlay (440px). No scrim; page
 * stays interactive so the operator can re-trigger drill from another row
 * without dismissing.
 *
 * Filters: source, recency (no-op v1), intensity. The verified-purchase
 * filter is hidden until BestBuy / Amazon retailer-review ingestion lands
 * (current corpus is Reddit + YouTube + articles only — none carry a
 * verified-purchase signal, so the filter would always read 0%). Filter
 * changes update the visible set immediately client-side.
 *
 * 11.2 takes a resolved `mentions` array (fixture data); 11.3 will swap to
 * fetching `/mentions?ids=...` on open.
 */

const PAGE_SIZE = 12;

export type SourceFilter = "all" | "reddit" | "bestbuy" | "amazon" | "youtube" | "article";
export type IntensityFilter = "all" | Intensity;

export interface EvidenceDrawerProps {
  open: boolean;
  aspect: string;
  productName: string;
  mentions: MentionView[];
  onClose: () => void;
  // 11.3.c — when Standalone opens the drawer it kicks off a /api/mentions
  // fetch; we open the drawer optimistically and render a loading / error
  // body until the fetch resolves. Showcase still passes mentions synchronously
  // and omits these.
  loading?: boolean;
  errorMessage?: string | null;
}

function matchesSource(m: MentionView, f: SourceFilter): boolean {
  if (f === "all") return true;
  return m.source_type.toLowerCase().startsWith(f);
}

function matchesIntensity(m: MentionView, f: IntensityFilter): boolean {
  if (f === "all") return true;
  return m.aspect_tags.some((t) => t.intensity === f);
}

export function EvidenceDrawer({
  open,
  aspect,
  productName,
  mentions,
  onClose,
  loading = false,
  errorMessage = null,
}: EvidenceDrawerProps): JSX.Element | null {
  const [source, setSource] = useState<SourceFilter>("all");
  const [intensity, setIntensity] = useState<IntensityFilter>("all");
  const [visible, setVisible] = useState(PAGE_SIZE);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    setVisible(PAGE_SIZE);
  }, [source, intensity, mentions]);

  const filtered = useMemo(
    () =>
      mentions.filter(
        (m) => matchesSource(m, source) && matchesIntensity(m, intensity),
      ),
    [mentions, source, intensity],
  );

  if (!open) return null;

  return (
    <aside
      role="complementary"
      aria-label={`Evidence for ${aspect}`}
      className={cn(
        "fixed inset-y-0 right-0 z-30 flex w-[440px] flex-col border-l border-border bg-surface shadow-card",
        "transition-transform duration-2 ease-aw",
        "animate-in slide-in-from-right",
      )}
    >
      <header className="shrink-0 border-b border-border px-4 pt-3 pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
              Evidence
            </span>
            <h2 className="text-base font-semibold text-fg">
              {filtered.length} of {mentions.length} mentions · {aspect}
            </h2>
            <span className="text-xs text-fg-secondary">{productName}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-fg-muted hover:bg-surface-alt hover:text-fg"
            aria-label="close evidence drawer"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
          <label className="flex flex-col gap-0.5">
            <span className="text-[11px] uppercase tracking-wide text-fg-muted">source</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as SourceFilter)}
              className="h-7 rounded-md border border-border bg-surface px-2 text-xs text-fg"
            >
              <option value="all">all</option>
              <option value="reddit">reddit</option>
              <option value="bestbuy">bestbuy</option>
              <option value="amazon">amazon</option>
              <option value="youtube">youtube</option>
              <option value="article">article</option>
            </select>
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[11px] uppercase tracking-wide text-fg-muted">intensity</span>
            <select
              value={intensity}
              onChange={(e) => setIntensity(e.target.value as IntensityFilter)}
              className="h-7 rounded-md border border-border bg-surface px-2 text-xs text-fg"
            >
              <option value="all">all</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[11px] uppercase tracking-wide text-fg-muted">recency</span>
            <select
              disabled
              className="h-7 cursor-not-allowed rounded-md border border-border bg-surface-alt px-2 text-xs text-fg-muted"
            >
              <option>all (v1)</option>
            </select>
          </label>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-surface-alt p-4">
        {loading ? (
          <p className="py-8 text-center text-xs text-fg-muted">
            Loading evidence…
          </p>
        ) : errorMessage !== null ? (
          <p className="py-8 text-center text-xs text-danger">
            Couldn't load evidence: {errorMessage}
          </p>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-xs text-fg-muted">
            no mentions match these filters.
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {filtered.slice(0, visible).map((m) => (
              <VerbatimCard key={m.mention_id} mention={m} />
            ))}
            {filtered.length > visible && (
              <button
                type="button"
                onClick={() => setVisible((n) => n + PAGE_SIZE)}
                className="mt-2 self-center rounded-md border border-border bg-surface px-3 py-1 text-xs font-medium text-fg hover:border-accent hover:text-accent"
              >
                Load more ({filtered.length - visible} remaining)
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
