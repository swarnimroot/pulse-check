import { useEffect, useState } from "react";
import { X } from "lucide-react";

/**
 * GlossaryButton + GlossaryDialog — non-technical onboarding affordance for
 * the three data pages (Standalone, Pair, Compare). Renders as a small
 * pill-style trigger; opens a centered modal grouped into five sections
 * (Unit · How we score · How we count · Head-to-head · Output) so a
 * stakeholder lands on a pipeline narrative rather than a flat term list.
 *
 * Same content on every page so vocabulary stays consistent across surfaces.
 */

interface TermDefinition {
  term: string;
  description: string;
  details?: string[];
}

interface GlossarySection {
  title: string;
  terms: TermDefinition[];
}

const SECTIONS: GlossarySection[] = [
  {
    title: "The unit",
    terms: [
      {
        term: "Mention",
        description:
          "One piece of public text we've ingested — a Reddit post or comment, a YouTube comment, or a fragment of a published review article.",
      },
    ],
  },
  {
    title: "How we score",
    terms: [
      {
        term: "Net sentiment",
        description:
          "Share of positive minus share of negative mentions on an aspect, scaled to [-1, +1]. A value of +0.40 means roughly 40 percentage points more positive than negative mentions. Every mention counts as 1.0 — no weighting by source, recency, or intensity.",
      },
      {
        term: "Intensity",
        description:
          "How forceful the language in a mention is — strong, medium, or weak. Surfaced as a separate signal alongside polarity counts; never folded into the net-sentiment number.",
      },
    ],
  },
  {
    title: "How we count",
    terms: [
      {
        term: "Primary, Secondary, Long-tail attribution",
        description:
          "The three buckets on a standalone product's aspect column:",
        details: [
          "Primary — top 3 aspects where the product is the direct subject of the mention.",
          "Secondary — top 3 aspects where the product is named in passing (e.g., a Razer review that names the Alienware 16 as a competitor).",
          "Long-tail — every remaining aspect with at least one mention. Low-signal but kept for completeness.",
        ],
      },
    ],
  },
  {
    title: "On the head-to-head",
    terms: [
      {
        term: "Leads, tied",
        description:
          "On any given aspect, a side leads when its net sentiment exceeds the other side's by more than 0.10. Gaps of 0.10 or smaller report as Tied. The leader's cell carries an accent ring.",
      },
    ],
  },
  {
    title: "The output",
    terms: [
      {
        term: "Brief",
        description:
          "A Sonnet-synthesized paragraph that summarizes a product's strengths and weaknesses. Every claim cites real mention IDs — the citation chips on each claim link back to the quotes — so nothing is paraphrased or invented by the model.",
      },
    ],
  },
];

export function GlossaryButton(): JSX.Element {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start rounded-md border border-accent-soft bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent transition-colors duration-1 ease-aw hover:border-accent hover:bg-accent-soft hover:text-accent-hover"
      >
        What are all these numbers?
      </button>
      {open && <GlossaryDialog onClose={() => setOpen(false)} />}
    </>
  );
}

interface GlossaryDialogProps {
  onClose: () => void;
}

function GlossaryDialog({ onClose }: GlossaryDialogProps): JSX.Element {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="glossary-title"
      className="fixed inset-0 z-50 flex items-start justify-center bg-fg/30 backdrop-blur-md px-6 py-12"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80vh] w-full max-w-[720px] flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-card"
      >
        <header className="flex items-start justify-between border-b border-border px-6 py-4">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
              Glossary
            </span>
            <h2 id="glossary-title" className="text-base font-semibold text-fg">
              What are all these numbers?
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close glossary"
            className="rounded-md p-1 text-fg-muted hover:bg-surface-alt hover:text-fg"
          >
            <X size={16} />
          </button>
        </header>
        <div className="flex flex-col gap-6 overflow-y-auto px-6 py-5">
          {SECTIONS.map((section, idx) => (
            <section
              key={section.title}
              className={
                idx === 0
                  ? "flex flex-col gap-3"
                  : "flex flex-col gap-3 border-t border-border pt-5"
              }
            >
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
                {section.title}
              </h3>
              <dl className="flex flex-col gap-4">
                {section.terms.map((t) => (
                  <div key={t.term} className="flex flex-col gap-1">
                    <dt className="text-sm font-semibold text-fg">{t.term}</dt>
                    <dd className="text-sm leading-relaxed text-fg-secondary">
                      {t.description}
                      {t.details && (
                        <ul className="mt-2 flex flex-col gap-1.5 pl-4 text-sm leading-relaxed text-fg-secondary">
                          {t.details.map((d) => (
                            <li key={d} className="list-disc">
                              {d}
                            </li>
                          ))}
                        </ul>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
