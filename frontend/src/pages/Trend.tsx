import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Select, type SelectOption } from "@/components/atoms";
import { GlossaryButton } from "@/components/GlossaryDialog";
import { TrendChart } from "@/components/TrendChart";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import {
  availableAspects,
  rollupAspect,
  type Granularity,
} from "@/lib/trendRollup";
import type { ProductSummary, TrendResponse } from "@/lib/types";

/**
 * Trend — per-aspect sentiment & volume over time for one product.
 *
 * Cascading Company → Product pickers (off the `brand` field) select a
 * product; the page fetches `/api/trend/{product_id}` (all weekly snapshots
 * for that product) and renders one aspect at a time as a sentiment line +
 * volume bars. A Week / Month / Year toggle rolls the weekly snapshots into
 * coarser buckets so the chart stays legible as history accrues (rollup +
 * volume-weighted net live in lib/trendRollup.ts — no backend aggregation).
 *
 * Trend points carry no mention_ids, so there's no evidence drill here; that
 * stays on the Standalone page.
 */

const ASPECT_LABELS: Record<string, string> = {
  thermals: "Thermals",
  performance: "Performance",
  keyboard: "Keyboard",
  display: "Display",
  battery: "Battery",
  build_quality: "Build quality",
  software_experience: "Software experience",
  price_value: "Price / value",
  support_warranty: "Support / warranty",
  aesthetics: "Aesthetics",
  portability: "Portability",
};

function aspectLabel(a: string): string {
  return ASPECT_LABELS[a] ?? a;
}

const GRANULARITIES: { value: Granularity; label: string }[] = [
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
  { value: "year", label: "Year" },
];

type ProductsState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; products: ProductSummary[] };

type TrendState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; trend: TrendResponse };

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

function netClass(v: number): string {
  if (v > 0.05) return "text-success";
  if (v < -0.05) return "text-danger";
  return "text-fg-muted";
}

function fmtNet(v: number): string {
  return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2);
}

function deltaLabel(v: number): string {
  const arrow = v > 0.001 ? "▲ " : v < -0.001 ? "▼ " : "= ";
  return arrow + fmtNet(v);
}

export function Trend(): JSX.Element {
  const [productsState, setProductsState] = useState<ProductsState>({ kind: "loading" });
  const [company, setCompany] = useState("");
  const [productId, setProductId] = useState("");
  const [trendState, setTrendState] = useState<TrendState>({ kind: "idle" });
  const [gran, setGran] = useState<Granularity>("month");
  const [aspect, setAspect] = useState("");

  // Load product list once.
  useEffect(() => {
    let cancelled = false;
    api
      .products()
      .then((res) => {
        if (!cancelled) setProductsState({ kind: "ready", products: res.products });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setProductsState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch trend whenever the selected product changes.
  useEffect(() => {
    if (!productId) {
      setTrendState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setTrendState({ kind: "loading" });
    api
      .trend(productId)
      .then((trend) => {
        if (!cancelled) setTrendState({ kind: "ready", trend });
      })
      .catch((err: unknown) => {
        if (!cancelled) setTrendState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  const companyOptions = useMemo<SelectOption[]>(() => {
    if (productsState.kind !== "ready") return [];
    const seen = new Set<string>();
    const out: SelectOption[] = [];
    for (const p of productsState.products) {
      if (!seen.has(p.brand)) {
        seen.add(p.brand);
        out.push({ value: p.brand, label: p.brand });
      }
    }
    return out;
  }, [productsState]);

  const productOptions = useMemo<SelectOption[]>(() => {
    if (productsState.kind !== "ready" || !company) return [];
    return productsState.products
      .filter((p) => p.brand === company)
      .map((p) => ({ value: p.product_id, label: p.display_name }));
  }, [productsState, company]);

  const aspects = useMemo<string[]>(
    () => (trendState.kind === "ready" ? availableAspects(trendState.trend.snapshots) : []),
    [trendState],
  );

  // Keep the selected aspect valid as the available set changes.
  useEffect(() => {
    if (aspects.length === 0) {
      if (aspect !== "") setAspect("");
      return;
    }
    if (!aspects.includes(aspect)) setAspect(aspects[0]);
  }, [aspects, aspect]);

  const handleCompanyChange = (next: string): void => {
    setCompany(next);
    setProductId("");
  };

  return (
    <div className="min-h-screen bg-surface text-fg">
      <main className="mx-auto flex max-w-[1400px] flex-col gap-6 px-8 py-8">
        <header className="flex items-start justify-between gap-6">
          <div className="flex flex-col gap-1">
            <Link
              to="/"
              className="self-start text-xs font-medium text-accent hover:text-accent-hover"
            >
              ← back
            </Link>
            <span className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
              Over time
            </span>
            <h1 className="text-xl font-semibold text-fg">Trend over time</h1>
            <p className="max-w-[680px] text-xs text-fg-muted">
              Pick a product to see how the public's sentiment and discussion
              volume on each aspect move week over week. Use the Week / Month /
              Year toggle to zoom the time axis — months and years roll the
              weekly snapshots up (volume summed, sentiment volume-weighted).
            </p>
          </div>
          <GlossaryButton />
        </header>

        <section className="rounded-md border border-border bg-surface p-5 shadow-card">
          <div className="grid max-w-[640px] grid-cols-2 gap-3">
            <Select
              label="Company"
              value={company}
              options={companyOptions}
              onChange={handleCompanyChange}
              disabled={productsState.kind !== "ready"}
              placeholder="Select a company"
            />
            <Select
              label="Product"
              value={productId}
              options={productOptions}
              onChange={setProductId}
              disabled={productsState.kind !== "ready" || productOptions.length === 0}
              placeholder={company ? "Select a product" : "Pick a company first"}
            />
          </div>
          {productsState.kind === "error" && (
            <p className="mt-3 text-xs text-danger">
              Couldn't load products: {productsState.message}
            </p>
          )}
        </section>

        <TrendBody
          trendState={trendState}
          aspects={aspects}
          aspect={aspect}
          onAspectChange={setAspect}
          gran={gran}
          onGranChange={setGran}
        />
      </main>
    </div>
  );
}

interface TrendBodyProps {
  trendState: TrendState;
  aspects: string[];
  aspect: string;
  onAspectChange: (a: string) => void;
  gran: Granularity;
  onGranChange: (g: Granularity) => void;
}

function TrendBody({
  trendState,
  aspects,
  aspect,
  onAspectChange,
  gran,
  onGranChange,
}: TrendBodyProps): JSX.Element {
  if (trendState.kind === "idle") {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-alt px-6 py-8 text-center">
        <p className="text-sm text-fg-secondary">
          Pick a product to see its sentiment and volume trend over time.
        </p>
        <p className="text-xs text-fg-muted">
          One line per aspect across weekly snapshots, with a Week / Month /
          Year zoom.
        </p>
      </div>
    );
  }
  if (trendState.kind === "loading") {
    return (
      <div className="flex flex-col gap-3" aria-label="Loading trend">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-[260px] w-full" />
      </div>
    );
  }
  if (trendState.kind === "error") {
    return (
      <div className="rounded-md border border-danger bg-danger-soft p-4">
        <p className="text-sm text-danger">
          Couldn't load trend: {trendState.message}
        </p>
      </div>
    );
  }

  const { trend } = trendState;
  if (trend.snapshots.length === 0 || aspects.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-alt px-6 py-8 text-center">
        <p className="text-sm text-fg-secondary">
          No weekly snapshots yet for {trend.display_name}.
        </p>
        <p className="text-xs text-fg-muted">
          The trend fills in as weekly analysis runs accrue — check back after
          the next weekly run.
        </p>
      </div>
    );
  }

  // Derive the active aspect at render time rather than trusting the
  // effect-synced `aspect` state: on the first render after the trend loads,
  // `aspect` is still "" (the effect runs post-render), which would roll up to
  // an empty bucket list and crash on `last.net`. Falling back to aspects[0]
  // keeps the first paint correct.
  const activeAspect = aspects.includes(aspect) ? aspect : aspects[0];
  const buckets = rollupAspect(trend.snapshots, activeAspect, gran);
  const granNoun = gran === "week" ? "weeks" : gran === "month" ? "months" : "years";

  // availableAspects guarantees activeAspect has ≥1 point, but guard anyway so
  // an unexpected empty rollup degrades gracefully instead of white-screening.
  if (buckets.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-alt px-6 py-8 text-center">
        <p className="text-sm text-fg-secondary">
          No data for {aspectLabel(activeAspect)} on {trend.display_name}.
        </p>
      </div>
    );
  }

  const last = buckets[buckets.length - 1];
  const prev = buckets.length > 1 ? buckets[buckets.length - 2] : null;

  return (
    <section className="flex flex-col gap-4 rounded-md border border-border bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-base font-semibold text-fg">{aspectLabel(activeAspect)}</h2>
          <p className="text-xs text-fg-muted">
            net sentiment &amp; mention volume · {buckets.length} {granNoun} shown
          </p>
        </div>
        <GranularityToggle gran={gran} onChange={onGranChange} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {aspects.map((a) => {
          const active = a === activeAspect;
          return (
            <button
              key={a}
              type="button"
              onClick={() => onAspectChange(a)}
              aria-pressed={active}
              className={
                active
                  ? "rounded-full border border-accent bg-accent px-2.5 py-1 text-xs font-medium text-fg-on-accent"
                  : "rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-fg-muted transition-colors duration-1 ease-aw hover:border-accent-soft hover:text-fg"
              }
            >
              {aspectLabel(a)}
            </button>
          );
        })}
      </div>

      <TrendChart buckets={buckets} />

      <div className="flex gap-3 text-xs text-fg-muted">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-0 w-4 border-t-2 border-accent"
          />
          net sentiment (−1…+1)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-3 rounded-sm border border-accent bg-accent-soft"
          />
          mention volume
        </span>
      </div>

      <div className="flex flex-wrap gap-8 border-t border-border pt-4 text-sm">
        <Stat label="Latest net">
          <span className={`tabular ${netClass(last.net)}`}>{fmtNet(last.net)}</span>
        </Stat>
        <Stat label="Latest volume">
          <span className="tabular text-fg">{last.vol}</span>
        </Stat>
        <Stat label={`${gran === "week" ? "Week" : gran === "month" ? "Month" : "Year"}-over-${gran === "week" ? "week" : gran === "month" ? "month" : "year"} delta`}>
          {prev ? (
            <span className={`tabular ${netClass(last.net - prev.net)}`}>
              {deltaLabel(last.net - prev.net)}
            </span>
          ) : (
            <span className="text-fg-muted">—</span>
          )}
        </Stat>
      </div>

      {buckets.length === 1 && (
        <p className="text-xs italic text-fg-muted">
          Only one snapshot so far — the line fills in as more weekly runs
          accrue.
        </p>
      )}
    </section>
  );
}

function GranularityToggle({
  gran,
  onChange,
}: {
  gran: Granularity;
  onChange: (g: Granularity) => void;
}): JSX.Element {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-border" role="group" aria-label="Time granularity">
      {GRANULARITIES.map((g) => {
        const active = g.value === gran;
        return (
          <button
            key={g.value}
            type="button"
            onClick={() => onChange(g.value)}
            aria-pressed={active}
            className={
              "border-r border-border px-3.5 py-1.5 text-xs font-semibold last:border-r-0 " +
              (active
                ? "bg-accent text-fg-on-accent"
                : "bg-surface text-fg-muted transition-colors duration-1 ease-aw hover:text-fg")
            }
          >
            {g.label}
          </button>
        );
      })}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className="text-lg font-semibold">{children}</span>
    </div>
  );
}
