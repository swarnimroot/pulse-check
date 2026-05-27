import { CiteChip } from "@/components/atoms";
import type { PairBriefNarrative } from "@/lib/types";

/**
 * PairBriefPanel — single-contrast-paragraph render for one product pair.
 *
 * Mirrors `BriefPanel.SummaryBlock` styling (accent left border, italic
 * surface-alt body) since the pair brief IS a one-paragraph contrast — the
 * Pair page scorecard supplies the per-aspect numerical detail; this panel
 * supplies the texture.
 *
 * Added session 42 (ARCHITECTURE §6.4 — pair brief layout).
 */

export interface PairBriefPanelProps {
  narrative: PairBriefNarrative;
  model?: string;
  promptVersion?: string;
  onCite: (claimText: string, citedMentionIds: string[]) => void;
}

export function PairBriefPanel({
  narrative,
  model,
  promptVersion,
  onCite,
}: PairBriefPanelProps): JSX.Element {
  const contrast = narrative.contrast;
  return (
    <article className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6 shadow-card">
      <header>
        <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          Pair brief{model ? ` · ${model}` : ""}
          {promptVersion ? ` · ${promptVersion}` : ""}
        </span>
        <h3 className="mt-1 text-base font-semibold text-fg">
          {narrative.brief_title}
        </h3>
      </header>
      <aside
        aria-label="Pair brief contrast"
        className="flex flex-col gap-1 border-l-2 border-accent/70 bg-surface-alt px-4 py-3"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
          Contrast
        </span>
        <p className="text-[13px] italic leading-[1.55] text-fg-secondary">
          {contrast.text}
          {contrast.cited_mention_ids.length > 0 && (
            <CiteChip
              count={contrast.cited_mention_ids.length}
              citedMentionIds={contrast.cited_mention_ids}
              onClick={(ids) => onCite(contrast.text, ids)}
            />
          )}
        </p>
      </aside>
    </article>
  );
}
