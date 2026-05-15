import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "@/lib/api";
import type {
  HomeSummary,
  PipelineStageStat,
  SourcesResponse,
} from "@/lib/types";

/**
 * Home — executive entry point (bite 32.b).
 *
 * Three card surface (Standalone / Head-to-head / Heatmap) over a one-line
 * run metadata strip, followed by a collapsible plain-English explainer
 * ("Under the hood") describing the single data pipeline that powers all
 * three views. Targets a non-technical first-time visitor — no jargon, no
 * mention-ID provenance details on this page; that lives in the drill-down
 * surfaces.
 */

// Manufacturer-POV anchor product for the "Open standalone" default. If the
// product isn't in the run, the Standalone page renders its own 404.
const STANDALONE_DEFAULT_PRODUCT_ID = "alienware_16_aurora";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; summary: HomeSummary };

type SourcesState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; sources: SourcesResponse };

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

export function About(): JSX.Element {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [hoodOpen, setHoodOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [sourcesState, setSourcesState] = useState<SourcesState>({ kind: "idle" });

  const toggleSources = (): void => {
    const nextOpen = !sourcesOpen;
    setSourcesOpen(nextOpen);
    // Lazy-fetch the first time the panel opens; reuse afterwards.
    if (nextOpen && sourcesState.kind === "idle") {
      setSourcesState({ kind: "loading" });
      api
        .sources()
        .then((sources) => setSourcesState({ kind: "ready", sources }))
        .catch((err: unknown) =>
          setSourcesState({ kind: "error", message: describeError(err) }),
        );
    }
  };

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .home()
      .then((summary) => {
        if (!cancelled) setState({ kind: "ready", summary });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <main className="min-h-screen bg-surface text-fg">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-10 px-8 py-14">
        <header className="flex flex-col gap-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
            pulse-check
          </span>
          <h1 className="text-2xl font-semibold text-fg">
            Product listening for executives.
          </h1>
          <p className="max-w-[680px] text-sm text-fg-secondary">
            Every aggregate on every screen was computed from real public
            mentions — Reddit threads, editorial reviews, and other public
            sources. Click any number to see the contributing quotes verbatim.
            Briefs cite the exact mentions they drew from.
          </p>
        </header>

        <section className="grid grid-cols-3 gap-4">
          <HomeCard
            eyebrow="Per product"
            title="Standalone voice"
            blurb="Single-product scorecard. What people love, what they complain about, across 11 aspects — ranked by mention count, every number drillable."
            cta="Open standalone →"
            to={`/standalone/${STANDALONE_DEFAULT_PRODUCT_ID}`}
          />
          <HomeCard
            eyebrow="Two products"
            title="Head-to-head comparison"
            blurb="Pick two products. See aspect-by-aspect where each one leads, with the underlying quotes one click away."
            cta="Open comparison →"
            to="/pair"
          />
          <HomeCard
            eyebrow="All products"
            title="Cross-product heatmap"
            blurb="Every tracked product across every aspect on one screen. Tinted by sentiment, click any cell to drill into verbatims."
            cta="Open heatmap →"
            to="/compare"
          />
        </section>

        <RunStrip state={state} onRetry={() => setReloadKey((k) => k + 1)} />

        <UnderTheHood
          open={hoodOpen}
          onToggle={() => setHoodOpen((v) => !v)}
          state={state}
          sourcesOpen={sourcesOpen}
          sourcesState={sourcesState}
          onToggleSources={toggleSources}
        />
      </div>
    </main>
  );
}

interface HomeCardProps {
  eyebrow: string;
  title: string;
  blurb: string;
  cta: string;
  to: string;
}

function HomeCard({ eyebrow, title, blurb, cta, to }: HomeCardProps): JSX.Element {
  return (
    <article className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6 shadow-card">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent">
          {eyebrow}
        </span>
        <h2 className="text-base font-semibold text-fg">{title}</h2>
        <p className="mt-1 text-sm text-fg-secondary">{blurb}</p>
      </div>
      <Link
        to={to}
        className="mt-auto text-sm font-medium text-accent hover:text-accent-hover"
      >
        {cta}
      </Link>
    </article>
  );
}

interface RunStripProps {
  state: LoadState;
  onRetry: () => void;
}

function RunStrip({ state, onRetry }: RunStripProps): JSX.Element {
  if (state.kind === "loading") {
    return <p className="text-xs text-fg-muted">Loading run summary…</p>;
  }
  if (state.kind === "error") {
    return (
      <div className="flex items-center gap-3 text-xs">
        <span className="text-danger">Couldn't load summary: {state.message}</span>
        <button
          type="button"
          onClick={onRetry}
          className="font-medium text-accent hover:text-accent-hover"
        >
          retry
        </button>
      </div>
    );
  }
  const { run_id, products_tracked, mentions_analyzed } = state.summary;
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
      <span>
        Run{" "}
        <code className="rounded bg-surface-alt px-1.5 py-0.5 text-[11px] text-fg">
          {run_id ?? "(none)"}
        </code>
      </span>
      <span>·</span>
      <span>{formatNumber(products_tracked)} products tracked</span>
      <span>·</span>
      <span>{formatNumber(mentions_analyzed)} public mentions analyzed</span>
    </p>
  );
}

interface UnderTheHoodProps {
  open: boolean;
  onToggle: () => void;
  state: LoadState;
  sourcesOpen: boolean;
  sourcesState: SourcesState;
  onToggleSources: () => void;
}

function UnderTheHood({
  open,
  onToggle,
  state,
  sourcesOpen,
  sourcesState,
  onToggleSources,
}: UnderTheHoodProps): JSX.Element {
  const stageCount =
    state.kind === "ready" ? state.summary.pipeline.length : null;
  return (
    <section className="flex flex-col gap-4">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex items-center justify-between rounded-md border border-border bg-surface-alt px-4 py-3 text-left transition-colors duration-1 ease-aw hover:bg-surface"
      >
        <span className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="inline-block text-xs text-fg-secondary"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            ▶
          </span>
          <span className="text-sm font-semibold text-fg">Under the hood</span>
          <span className="text-xs text-fg-muted">
            What runs between product selection and the result you see
          </span>
        </span>
        {stageCount !== null && (
          <span className="text-xs text-fg-muted">
            {stageCount} stages · 1 pipeline
          </span>
        )}
      </button>

      {open && state.kind === "ready" && (
        <PipelineExplainer
          stages={state.summary.pipeline}
          sourcesOpen={sourcesOpen}
          sourcesState={sourcesState}
          onToggleSources={onToggleSources}
        />
      )}
      {open && state.kind === "loading" && (
        <p className="text-sm text-fg-muted">Loading pipeline…</p>
      )}
      {open && state.kind === "error" && (
        <p className="text-sm text-danger">Couldn't load pipeline: {state.message}</p>
      )}
    </section>
  );
}

interface PipelineExplainerProps {
  stages: PipelineStageStat[];
  sourcesOpen: boolean;
  sourcesState: SourcesState;
  onToggleSources: () => void;
}

function PipelineExplainer({
  stages,
  sourcesOpen,
  sourcesState,
  onToggleSources,
}: PipelineExplainerProps): JSX.Element {
  return (
    <div className="flex flex-col gap-4 rounded-md border border-border bg-surface p-5 shadow-card">
      <p className="text-xs text-fg-muted">
        One pipeline runs once per product set. All three views above read off
        the same numbers.
      </p>
      <div className="-mx-2 overflow-x-auto pb-2">
        <ol className="flex min-w-min items-stretch gap-3 px-2">
          {stages.map((stage, idx) => (
            <li key={stage.key} className="flex items-stretch gap-3">
              <StageCard stage={stage} index={idx + 1} />
              {idx < stages.length - 1 && (
                <span
                  aria-hidden="true"
                  className="flex items-center text-fg-muted"
                >
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>
      <div className="flex flex-col gap-2 rounded-sm border border-border bg-surface-alt p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          …feeds all three views above
        </p>
        <ul className="grid grid-cols-3 gap-3 text-xs text-fg-secondary">
          <li>
            <span className="font-medium text-fg">Standalone</span> — one
            product's scorecard + brief.
          </li>
          <li>
            <span className="font-medium text-fg">Head-to-head</span> — same
            scorecard for two products, side by side.
          </li>
          <li>
            <span className="font-medium text-fg">Heatmap</span> — every
            product's scores in one matrix.
          </li>
        </ul>
      </div>
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={onToggleSources}
          aria-expanded={sourcesOpen}
          className="flex items-center justify-between rounded-sm border border-border bg-surface-alt px-3 py-2 text-left transition-colors duration-1 ease-aw hover:bg-surface"
        >
          <span className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block text-xs text-fg-secondary"
              style={{
                transform: sourcesOpen ? "rotate(90deg)" : "rotate(0deg)",
              }}
            >
              ▶
            </span>
            <span className="text-sm font-medium text-fg">
              Show all sources
            </span>
            <span className="text-xs text-fg-muted">
              The Reddit communities, YouTube channels, and review sites we
              listen to
            </span>
          </span>
        </button>
        {sourcesOpen && <SourcesPanel state={sourcesState} />}
      </div>
    </div>
  );
}

function SourcesPanel({ state }: { state: SourcesState }): JSX.Element {
  if (state.kind === "idle" || state.kind === "loading") {
    return <p className="text-xs text-fg-muted">Loading sources…</p>;
  }
  if (state.kind === "error") {
    return (
      <p className="text-xs text-danger">
        Couldn't load sources: {state.message}
      </p>
    );
  }
  const { reddit, youtube, review_sites } = state.sources;
  const maxRows = Math.max(reddit.length, youtube.length, review_sites.length);
  return (
    <div className="overflow-x-auto rounded-sm border border-border bg-surface">
      <table className="w-full table-fixed text-left text-xs">
        <thead>
          <tr className="border-b border-border bg-surface-alt">
            <th className="px-3 py-2 font-semibold uppercase tracking-wide text-fg-secondary">
              Reddit ({reddit.length})
            </th>
            <th className="px-3 py-2 font-semibold uppercase tracking-wide text-fg-secondary">
              YouTube ({youtube.length})
            </th>
            <th className="px-3 py-2 font-semibold uppercase tracking-wide text-fg-secondary">
              Review sites ({review_sites.length})
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: maxRows }).map((_, i) => (
            <tr key={i} className="border-b border-border last:border-b-0">
              <td className="px-3 py-1.5 text-fg-secondary">
                {reddit[i]?.name ?? ""}
              </td>
              <td className="px-3 py-1.5 text-fg-secondary">
                {youtube[i]?.name ?? ""}
              </td>
              <td className="px-3 py-1.5 text-fg-secondary">
                {review_sites[i]?.name ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StageCard({
  stage,
  index,
}: {
  stage: PipelineStageStat;
  index: number;
}): JSX.Element {
  return (
    <div className="flex w-[260px] flex-shrink-0 flex-col gap-3 rounded-md border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-sm bg-surface-alt px-1.5 text-[11px] font-semibold text-fg-secondary">
            {index}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
            {stage.label}
          </span>
        </div>
        {stage.ai && (
          <span className="inline-flex items-center gap-1 rounded-sm bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent-hover">
            <span aria-hidden="true">●</span>
            <span>AI</span>
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <h3 className="text-sm font-semibold text-fg">{stage.title}</h3>
        <p className="text-xs leading-relaxed text-fg-secondary">
          {stage.description}
        </p>
      </div>
      {stage.chips.length > 0 && (
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {stage.chips.map((chip) => (
            <span
              key={chip.name}
              className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-surface-alt px-1.5 py-0.5 text-[10px] font-medium text-fg-secondary"
            >
              <span className="uppercase tracking-wide text-fg-muted">
                {chip.name}
              </span>
              <span className="tabular text-fg">
                {typeof chip.value === "number"
                  ? formatNumber(chip.value)
                  : chip.value}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
