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
import { AspectColumn } from "@/components/AspectColumn";
import { BriefPanel } from "@/components/BriefPanel";
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

/**
 * Showcase — renders every atom + composite against fixture data so an
 * operator can visually confirm the design system in a browser. NOT a
 * production page; the real Standalone / Compare pages live in
 * `pages/Standalone.tsx` and `pages/Compare.tsx` (bite 11.3.b).
 *
 * BriefPanel was extracted from this file in bite 11.3.b so Standalone
 * can mount it directly; this page now imports it like any consumer.
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
            ← back to index
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

        {/* Aspect rows — two polarity scrollers per DESIGN_SYSTEM §5.1.
            Each scroller partitions into Primary / Secondary / Long-tail and
            uses one outer scroll cap to anchor the Brief below at a stable y.
            Click → drawer shows the bucket-relevant mention_ids (PRIMARY vs
            SECONDARY pools differ). */}
        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">{sampleProduct.display_name} — aspect summary</h2>
          <div className="grid grid-cols-2 gap-4">
            <AspectColumn
              title="What's working"
              polarity="positive"
              rows={sampleProduct.aspects}
              onRowClick={(row, bucket) =>
                openDrawer(
                  row.aspect,
                  bucket === "primary" ? row.mention_ids : row.mention_ids_secondary,
                )
              }
            />
            <AspectColumn
              title="What's not working"
              polarity="negative"
              rows={sampleProduct.aspects}
              onRowClick={(row, bucket) =>
                openDrawer(
                  row.aspect,
                  bucket === "primary" ? row.mention_ids : row.mention_ids_secondary,
                )
              }
            />
          </div>
          <p className="text-xs text-fg-muted">
            Each scroller partitions into Primary (top-3 by primary mentions),
            Secondary (top-3 by secondary mentions, deduped against Primary),
            and Long-tail. The bucket chip on each row names which bucket the
            metrics belong to.
          </p>
        </section>

        {/* Brief — extracted to BriefPanel in bite 11.3.b. */}
        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">a1 brief — citation panel demo</h2>
          <BriefPanel
            narrative={sampleBrief.narrative}
            model={sampleBrief.model}
            promptVersion={sampleBrief.prompt_version}
            onCite={openCitation}
          />
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
