import { CiteChip } from "@/components/atoms";
import type { BriefNarrative, BriefSummary, Claim } from "@/lib/types";

/**
 * BriefPanel — A1 brief render, collapsed 4 → 2 sections at UI time.
 *
 * Backend §6.3 contract still produces 4 quadrants (Q1 PRIMARY pos / Q2
 * PRIMARY neg / Q3 SECONDARY pos / Q4 SECONDARY neg); this component
 * merges PRIMARY+SECONDARY per polarity and caps at 5 bullets per
 * section, PRIMARY claims listed first. Locked session 15.
 *
 * Extracted from Showcase in bite 11.3.b so Standalone can mount it
 * directly.
 */

const MAX_CLAIMS_PER_BLOCK = 5;

// Polarity routing matches both fixture headings ("What's working" /
// "What's not working") and live Sonnet headings ("High-confidence strengths"
// / "...weaknesses" / "Low-signal strengths..." / "...weaknesses..."). Negative
// keywords ("not working", "weakness") are checked first so a heading that
// somehow combines tokens routes to negative (the safer mis-classification —
// it surfaces the claim with a red dot rather than dropping it). "weakness" /
// "strength" are singular substrings so they catch both singular and plural.
function bucketBriefByPolarity(narrative: BriefNarrative): {
  positive: Claim[];
  negative: Claim[];
} {
  const positive: Claim[] = [];
  const negative: Claim[] = [];
  for (const section of narrative.sections) {
    const heading = section.heading.toLowerCase();
    if (heading.includes("not working") || heading.includes("weakness")) {
      negative.push(...section.claims);
    } else if (heading.includes("working") || heading.includes("strength")) {
      positive.push(...section.claims);
    }
  }
  return {
    positive: positive.slice(0, MAX_CLAIMS_PER_BLOCK),
    negative: negative.slice(0, MAX_CLAIMS_PER_BLOCK),
  };
}

interface BriefBlockProps {
  heading: string;
  claims: Claim[];
  onCite: (claimText: string, citedMentionIds: string[]) => void;
}

function BriefBlock({ heading, claims, onCite }: BriefBlockProps): JSX.Element {
  const isPositive = !heading.toLowerCase().includes("not");
  return (
    <div className="flex flex-col gap-2">
      <h4 className="flex items-center gap-2 text-base font-semibold text-fg">
        <span
          aria-hidden
          className={`inline-block h-2 w-2 rounded-full ${
            isPositive ? "bg-success" : "bg-danger"
          }`}
        />
        {heading}
      </h4>
      {claims.length === 0 ? (
        <p className="text-sm italic text-fg-muted">No claims surfaced for this bucket.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {claims.map((claim, idx) => (
            <li
              key={`${heading}-${idx}`}
              className="flex flex-col gap-1 rounded-sm border-l-2 border-border bg-surface-alt px-3 py-2"
            >
              {claim.header && (
                <span className="text-sm font-semibold leading-[1.35] text-fg">
                  {claim.header}
                </span>
              )}
              <span className="text-[13px] leading-[1.5] text-fg-secondary">
                {claim.claim_text}
                {claim.cited_mention_ids.length > 0 && (
                  <CiteChip
                    count={claim.cited_mention_ids.length}
                    citedMentionIds={claim.cited_mention_ids}
                    onClick={(ids) => onCite(claim.claim_text, ids)}
                  />
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface BriefPanelProps {
  narrative: BriefNarrative;
  model?: string;
  promptVersion?: string;
  onCite: (claimText: string, citedMentionIds: string[]) => void;
}

interface SummaryBlockProps {
  summary: BriefSummary;
  onCite: (claimText: string, citedMentionIds: string[]) => void;
}

function SummaryBlock({ summary, onCite }: SummaryBlockProps): JSX.Element {
  return (
    <aside
      aria-label="Brief summary"
      className="flex flex-col gap-1 border-l-2 border-accent/70 bg-surface-alt px-4 py-3"
    >
      <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        Summary
      </span>
      <p className="text-[13px] italic leading-[1.55] text-fg-secondary">
        {summary.text}
        {summary.cited_mention_ids.length > 0 && (
          <CiteChip
            count={summary.cited_mention_ids.length}
            citedMentionIds={summary.cited_mention_ids}
            onClick={(ids) => onCite(summary.text, ids)}
          />
        )}
      </p>
    </aside>
  );
}

export function BriefPanel({
  narrative,
  model,
  promptVersion,
  onCite,
}: BriefPanelProps): JSX.Element {
  const buckets = bucketBriefByPolarity(narrative);
  return (
    <article className="flex flex-col gap-5 rounded-md border border-border bg-surface p-6 shadow-card">
      <header>
        <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          Brief{model ? ` · ${model}` : ""}
          {promptVersion ? ` · ${promptVersion}` : ""}
        </span>
        <h3 className="mt-1 text-base font-semibold text-fg">
          {narrative.brief_title}
        </h3>
      </header>
      {narrative.summary && (
        <SummaryBlock summary={narrative.summary} onCite={onCite} />
      )}
      <BriefBlock heading="What's working" claims={buckets.positive} onCite={onCite} />
      <BriefBlock heading="What's not working" claims={buckets.negative} onCite={onCite} />
    </article>
  );
}
