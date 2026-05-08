import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Chip,
  CiteChip,
  DrillNumber,
  IntensityBar,
  SourceDots,
  SourceMark,
  Sparkline,
  VerbatimCard,
} from "@/components/atoms";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { CitationPanel } from "@/components/CitationPanel";
import { RunMetaStrip } from "@/components/RunMetaStrip";
import {
  sampleBrief,
  sampleMentions,
  sampleProduct,
  sampleRunMeta,
  sampleSparklineData,
} from "@/fixtures/sample";
import type { ChipTone } from "@/components/atoms";
import type { AspectRow, BriefNarrative, Claim } from "@/lib/types";

/**
 * Showcase — renders every atom + composite against fixture data so an
 * operator can visually confirm bite 11.2 in a browser. NOT a production
 * page; bite 11.3 builds the real Standalone / Compare pages and routes.
 */

const CHIP_TONES: ChipTone[] = [
  "pos",
  "neg",
  "neu",
  "high",
  "med",
  "low",
  "messaging",
  "software",
  "hardware",
  "pricing",
  "mixed",
  "meta",
  "verified",
  "tombstone",
];

const SOURCES = ["reddit", "bestbuy", "amazon", "youtube", "article"];

const MAX_CLAIMS_PER_BLOCK = 5;

function bucketBriefByPolarity(narrative: BriefNarrative): {
  positive: Claim[];
  negative: Claim[];
} {
  const positive: Claim[] = [];
  const negative: Claim[] = [];
  for (const section of narrative.sections) {
    const heading = section.heading.toLowerCase();
    if (heading.includes("not working")) {
      negative.push(...section.claims);
    } else if (heading.includes("working")) {
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
        <ul className="flex flex-col gap-2">
          {claims.map((claim, idx) => (
            <li
              key={`${heading}-${idx}`}
              className="text-sm leading-[1.5] text-fg-secondary"
            >
              {claim.claim_text}
              {claim.cited_mention_ids.length > 0 && (
                <CiteChip
                  count={claim.cited_mention_ids.length}
                  citedMentionIds={claim.cited_mention_ids}
                  onClick={(ids) => onCite(claim.claim_text, ids)}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface AspectColumnProps {
  title: string;
  rows: AspectRow[];
  onRowClick: (row: AspectRow) => void;
}

// Shared grid template so the column-header row and each data row align.
//   aspect (flex) · sentiment · intensity · verified · mentions
const ROW_GRID = "grid-cols-[minmax(0,1fr)_72px_104px_72px_72px]";

function AspectColumn({ title, rows, onRowClick }: AspectColumnProps): JSX.Element {
  return (
    <div className="flex flex-col rounded-md border border-border bg-surface shadow-card">
      <div className="border-b border-border bg-surface-alt px-4 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">{title}</h3>
      </div>
      <div
        className={`grid ${ROW_GRID} items-center gap-3 border-b border-border bg-surface px-4 py-1.5 text-[10px] font-medium uppercase tracking-wide text-fg-muted`}
      >
        <span>aspect</span>
        <span className="text-center" title="net sentiment, −1 to +1">sentiment</span>
        <span className="text-center" title="share of mentions by intensity (high · med · low)">
          intensity
        </span>
        <span className="text-right" title="% of mentions from verified-purchase reviewers">
          verified
        </span>
        <span className="text-right" title="total mentions for this aspect">mentions</span>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-sm italic text-fg-muted">No aspects in this bucket.</p>
      ) : (
        <ul className="flex flex-col">
          {rows.map((row) => {
            const tone: ChipTone =
              row.net_sentiment > 0.15 ? "pos" : row.net_sentiment < -0.15 ? "neg" : "neu";
            const sign = row.net_sentiment >= 0 ? "+" : "";
            return (
              <li key={row.aspect} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => onRowClick(row)}
                  title={`open evidence for ${row.aspect}`}
                  className={`grid ${ROW_GRID} w-full cursor-zoom-in items-center gap-3 bg-transparent px-4 py-3 text-left transition-colors duration-1 ease-aw hover:bg-surface-alt`}
                >
                  <span className="truncate text-sm font-medium text-fg">{row.aspect}</span>
                  <span className="flex justify-center">
                    <Chip tone={tone}>
                      {sign}
                      {row.net_sentiment.toFixed(2)}
                    </Chip>
                  </span>
                  <span className="flex justify-center">
                    <IntensityBar intensityCounts={row.intensity_counts} width={96} />
                  </span>
                  <span className="tabular text-right text-xs text-fg-secondary">
                    {row.verified_pct.toFixed(0)}%
                  </span>
                  <span className="tabular text-right text-sm text-fg-secondary">
                    {row.total_mentions}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

interface PanelState {
  open: boolean;
  claimText: string;
  mentionIds: string[];
}

export function Showcase(): JSX.Element {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerAspect, setDrawerAspect] = useState("build_quality");
  const [drawerIds, setDrawerIds] = useState<string[]>([]);

  const [panel, setPanel] = useState<PanelState>({
    open: false,
    claimText: "",
    mentionIds: [],
  });

  const drawerMentions = useMemo(() => {
    if (drawerIds.length === 0) return sampleMentions;
    const set = new Set(drawerIds);
    const matched = sampleMentions.filter((m) => set.has(m.mention_id));
    return matched.length > 0 ? matched : sampleMentions;
  }, [drawerIds]);

  const panelMentions = useMemo(
    () =>
      panel.mentionIds
        .map((id) => sampleMentions.find((m) => m.mention_id === id))
        .filter((m): m is (typeof sampleMentions)[number] => m !== undefined),
    [panel.mentionIds],
  );

  const openDrawer = (aspect: string, ids: string[]): void => {
    setDrawerAspect(aspect);
    setDrawerIds(ids);
    setDrawerOpen(true);
  };

  const openCitation = (claimText: string, citedMentionIds: string[]): void => {
    setPanel({ open: true, claimText, mentionIds: citedMentionIds });
  };

  return (
    <div className="min-h-screen bg-surface text-fg">
      <RunMetaStrip
        totalMentions={sampleRunMeta.total_mentions}
        windowLabel={sampleRunMeta.window_label}
        lastRefreshed={sampleRunMeta.last_refreshed}
      />

      <main className="mx-auto flex max-w-[1200px] flex-col gap-12 px-8 py-10">
        <header className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-fg-muted">
            bite 11.2 · fixture-only
          </span>
          <h1 className="text-xl font-semibold text-fg">design-system showcase</h1>
          <p className="text-sm text-fg-secondary">
            Atoms, composites, and a synthetic A1 brief rendered against in-memory fixture
            data. Clicking aggregates opens the EvidenceDrawer; clicking a citation chip
            opens the CitationPanel.
          </p>
          <Link
            to="/"
            className="mt-2 self-start text-xs font-medium text-accent hover:text-accent-hover"
          >
            ← back to landing
          </Link>
        </header>

        {/* Atoms gallery */}
        <section className="flex flex-col gap-5">
          <h2 className="text-md text-fg">atoms</h2>

          <div className="rounded-md border border-border bg-surface p-5 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              Chip — every tone
            </h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {CHIP_TONES.map((tone) => (
                <Chip key={tone} tone={tone}>
                  {tone}
                </Chip>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-border bg-surface p-5 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              DrillNumber · CiteChip
            </h3>
            <div className="mt-3 flex flex-wrap items-center gap-6 text-sm">
              <span>
                non-interactive <DrillNumber value={1143} />
              </span>
              <span>
                hover &amp; click{" "}
                <DrillNumber
                  value={47}
                  onClick={() => openDrawer("build_quality", ["m_001", "m_007"])}
                  title="open evidence for build quality"
                />
              </span>
              <span>
                claim ends with citation
                <CiteChip
                  count={3}
                  citedMentionIds={["m_001", "m_004", "m_006"]}
                  onClick={(ids) =>
                    openCitation(
                      "Build quality is the standout strength of the Aurora 16.",
                      ids,
                    )
                  }
                />
              </span>
            </div>
          </div>

          <div className="rounded-md border border-border bg-surface p-5 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              SourceMark · SourceDots
            </h3>
            <div className="mt-3 flex flex-wrap items-center gap-6 text-sm">
              <span className="flex items-center gap-2">
                {SOURCES.map((s) => (
                  <SourceMark key={s} source={s} />
                ))}
                <span className="text-fg-muted">small (12px)</span>
              </span>
              <span className="flex items-center gap-2">
                {SOURCES.map((s) => (
                  <SourceMark key={s} source={s} size="md" />
                ))}
                <span className="text-fg-muted">medium (14px)</span>
              </span>
              <span className="flex items-center gap-2">
                <SourceDots sources={["reddit_post", "youtube", "article"]} />
                <span className="text-fg-muted">3 of 5 present</span>
              </span>
              <span className="flex items-center gap-2">
                <SourceDots sources={SOURCES} />
                <span className="text-fg-muted">all 5</span>
              </span>
            </div>
          </div>

          <div className="rounded-md border border-border bg-surface p-5 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              IntensityBar · Sparkline
            </h3>
            <div className="mt-3 flex flex-wrap items-center gap-6 text-sm">
              <span className="flex items-center gap-2">
                <IntensityBar intensityCounts={{ high: 18, medium: 22, low: 7 }} />
                <span className="text-fg-muted">build_quality</span>
              </span>
              <span className="flex items-center gap-2">
                <IntensityBar intensityCounts={{ high: 5, medium: 11, low: 13 }} />
                <span className="text-fg-muted">battery</span>
              </span>
              <span className="flex items-center gap-2">
                <Sparkline data={sampleSparklineData} />
                <span className="text-fg-muted">26-week recency</span>
              </span>
            </div>
          </div>

          <div className="rounded-md border border-border bg-surface p-5 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              VerbatimCard
            </h3>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <VerbatimCard mention={sampleMentions[0]} />
              <VerbatimCard mention={sampleMentions[3]} />
            </div>
          </div>
        </section>

        {/* Aspect rows — two-column positive / negative split. Each row clickable;
            full row open the drawer for that aspect. Drops intensity / sources /
            recency / verified from the first view per session-15 operator preference;
            those re-surface in the drawer or in an expanded-row view in 11.3. */}
        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">{sampleProduct.display_name} — aspect summary</h2>
          <div className="grid grid-cols-2 gap-4">
            <AspectColumn
              title="What's working"
              rows={sampleProduct.aspects
                .filter((r) => r.net_sentiment >= 0)
                .sort((a, b) => b.net_sentiment - a.net_sentiment)}
              onRowClick={(row) => openDrawer(row.aspect, row.mention_ids)}
            />
            <AspectColumn
              title="What's not working"
              rows={sampleProduct.aspects
                .filter((r) => r.net_sentiment < 0)
                .sort((a, b) => a.net_sentiment - b.net_sentiment)}
              onRowClick={(row) => openDrawer(row.aspect, row.mention_ids)}
            />
          </div>
          <p className="text-xs text-fg-muted">
            Each row opens the evidence drawer. Sort within each column is by signal
            magnitude (strongest sentiment first).
          </p>
        </section>

        {/* Brief — collapsed 4 → 2 sections at render time per session-15 preference.
            Backend §6.3 contract still produces 4 quadrants (Q1 PRIMARY pos / Q2 PRIMARY neg
            / Q3 SECONDARY pos / Q4 SECONDARY neg); this view merges PRIMARY+SECONDARY and
            caps at 5 bullets per section, PRIMARY claims listed first. */}
        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">a1 brief — citation panel demo</h2>
          <article className="flex flex-col gap-5 rounded-md border border-border bg-surface p-6 shadow-card">
            <header>
              <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
                Brief · {sampleBrief.model} · {sampleBrief.prompt_version}
              </span>
              <h3 className="mt-1 text-base font-semibold text-fg">
                {sampleBrief.narrative.brief_title}
              </h3>
            </header>
            {(() => {
              const buckets = bucketBriefByPolarity(sampleBrief.narrative);
              return (
                <>
                  <BriefBlock
                    heading="What's working"
                    claims={buckets.positive}
                    onCite={openCitation}
                  />
                  <BriefBlock
                    heading="What's not working"
                    claims={buckets.negative}
                    onCite={openCitation}
                  />
                </>
              );
            })()}
          </article>
        </section>

        {/* Manual drawer trigger */}
        <section className="flex flex-col gap-2">
          <h2 className="text-md text-fg">manual drawer trigger</h2>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => openDrawer("all aspects", [])}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-fg-on-accent hover:bg-accent-hover"
            >
              Open EvidenceDrawer (all 12 fixture mentions)
            </button>
            <button
              type="button"
              onClick={() =>
                openCitation("Sample standalone claim with 2 cited mentions.", ["m_001", "m_002"])
              }
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-fg hover:border-accent hover:text-accent"
            >
              Open CitationPanel (sample claim)
            </button>
          </div>
          <p className="text-xs text-fg-muted">
            With both open, the CitationPanel offsets to right=440 so both panels are visible
            simultaneously.
          </p>
        </section>
      </main>

      <EvidenceDrawer
        open={drawerOpen}
        aspect={drawerAspect}
        productName={sampleProduct.display_name}
        mentions={drawerMentions}
        onClose={() => setDrawerOpen(false)}
      />
      <CitationPanel
        open={panel.open}
        claimText={panel.claimText}
        mentions={panelMentions}
        offsetForDrawer={drawerOpen}
        onClose={() => setPanel((p) => ({ ...p, open: false }))}
      />
    </div>
  );
}
