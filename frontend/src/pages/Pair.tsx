import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Select, type SelectOption } from "@/components/atoms";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { GlossaryButton } from "@/components/GlossaryDialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import type {
  MentionView,
  PairAspectRow,
  PairResponse,
  ProductSummary,
} from "@/lib/types";

/**
 * Pair — head-to-head A1-based comparison (bite 32.b).
 *
 * Two side-by-side product pickers (Company → Product) at the top; once both
 * are chosen, the page fetches `/api/pair` and renders an aspect-by-aspect
 * scorecard plus a "leads on N of 11" headline. Each side's cell is
 * independently clickable — opens the existing EvidenceDrawer scoped to
 * that (product, aspect) tuple.
 *
 * Quantification semantics are spelled out for non-technical visitors:
 *   - "Net sentiment" is the share of positive minus share of negative
 *     mentions, normalized to [-1, +1].
 *   - "Leads" = net sentiment higher by more than 0.10 (backend threshold).
 */

// Operator decision (session 32): the pair page starts empty — visitor must
// explicitly choose both sides. No default product is pre-loaded.

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

type ProductsState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; products: ProductSummary[] };

type PairState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; pair: PairResponse };

interface DrawerState {
  open: boolean;
  aspect: string;
  productName: string;
  loading: boolean;
  mentions: MentionView[];
  errorMessage: string | null;
}

const INITIAL_DRAWER: DrawerState = {
  open: false,
  aspect: "",
  productName: "",
  loading: false,
  mentions: [],
  errorMessage: null,
};

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

function netSentTone(net: number): "pos" | "neg" | "neu" {
  if (net > 0.15) return "pos";
  if (net < -0.15) return "neg";
  return "neu";
}

function netSentBg(tone: "pos" | "neg" | "neu"): string {
  if (tone === "pos") return "bg-success-soft text-fg";
  if (tone === "neg") return "bg-danger-soft text-fg";
  return "bg-warning-soft text-fg";
}


export function Pair(): JSX.Element {
  const [productsState, setProductsState] = useState<ProductsState>({
    kind: "loading",
  });
  const [primaryCompany, setPrimaryCompany] = useState<string>("");
  const [primaryId, setPrimaryId] = useState<string>("");
  const [competitorCompany, setCompetitorCompany] = useState<string>("");
  const [competitorId, setCompetitorId] = useState<string>("");
  const [pairState, setPairState] = useState<PairState>({ kind: "idle" });
  const [drawer, setDrawer] = useState<DrawerState>(INITIAL_DRAWER);

  // Load product set once. No default selection: the visitor picks both
  // sides explicitly (session-32 operator decision).
  useEffect(() => {
    let cancelled = false;
    api
      .products()
      .then((res) => {
        if (cancelled) return;
        setProductsState({ kind: "ready", products: res.products });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setProductsState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-fetch the pair comparison whenever both products are set and differ.
  useEffect(() => {
    if (!primaryId || !competitorId) return;
    if (primaryId === competitorId) {
      setPairState({
        kind: "error",
        message: "Primary and competitor must differ.",
      });
      return;
    }
    let cancelled = false;
    setPairState({ kind: "loading" });
    api
      .pair(primaryId, competitorId)
      .then((pair) => {
        if (!cancelled) setPairState({ kind: "ready", pair });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setPairState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [primaryId, competitorId]);

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

  const primaryProductOptions = useMemo<SelectOption[]>(() => {
    if (productsState.kind !== "ready" || !primaryCompany) return [];
    return productsState.products
      .filter((p) => p.brand === primaryCompany)
      .map((p) => ({ value: p.product_id, label: p.display_name }));
  }, [productsState, primaryCompany]);

  const competitorProductOptions = useMemo<SelectOption[]>(() => {
    if (productsState.kind !== "ready" || !competitorCompany) return [];
    return productsState.products
      .filter((p) => p.brand === competitorCompany)
      .map((p) => ({ value: p.product_id, label: p.display_name }));
  }, [productsState, competitorCompany]);

  const handlePrimaryCompanyChange = (next: string): void => {
    setPrimaryCompany(next);
    // No auto-pick — the visitor explicitly chooses the product. Clear any
    // stale product id from a different brand so the dropdown reads empty.
    setPrimaryId("");
  };

  const handleCompetitorCompanyChange = (next: string): void => {
    setCompetitorCompany(next);
    setCompetitorId("");
  };

  const openCellDrawer = useCallback(
    (
      productName: string,
      aspect: string,
      mentionIds: string[],
    ): void => {
      setDrawer({
        open: true,
        aspect,
        productName,
        loading: true,
        mentions: [],
        errorMessage: null,
      });
      api
        .mentions(mentionIds)
        .then((res) => {
          setDrawer((prev) =>
            prev.open &&
            prev.aspect === aspect &&
            prev.productName === productName
              ? { ...prev, loading: false, mentions: res.mentions }
              : prev,
          );
        })
        .catch((err: unknown) => {
          setDrawer((prev) =>
            prev.open &&
            prev.aspect === aspect &&
            prev.productName === productName
              ? {
                  ...prev,
                  loading: false,
                  errorMessage: describeError(err),
                }
              : prev,
          );
        });
    },
    [],
  );

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
              Two products
            </span>
            <h1 className="text-xl font-semibold text-fg">
              Head-to-head comparison
            </h1>
            <p className="max-w-[680px] text-xs text-fg-muted">
              Pick two products. Each row below is one aspect of the laptop —
              we show how positively or negatively the public talks about it
              for each side, and which side leads. Click any cell to read the
              quotes behind the score.
            </p>
          </div>
          <GlossaryButton />
        </header>

        <section className="grid grid-cols-[1fr_auto_1fr] items-end gap-6 rounded-md border border-border bg-surface p-5 shadow-card">
          <PickerColumn
            company={primaryCompany}
            companyOptions={companyOptions}
            onCompanyChange={handlePrimaryCompanyChange}
            productId={primaryId}
            productOptions={primaryProductOptions}
            onProductChange={setPrimaryId}
            disabled={productsState.kind !== "ready"}
          />
          <div
            aria-hidden="true"
            className="self-stretch border-l border-border"
          />
          <PickerColumn
            company={competitorCompany}
            companyOptions={companyOptions}
            onCompanyChange={handleCompetitorCompanyChange}
            productId={competitorId}
            productOptions={competitorProductOptions}
            onProductChange={setCompetitorId}
            disabled={productsState.kind !== "ready"}
          />
        </section>

        <PairBody
          pairState={pairState}
          onCellClick={openCellDrawer}
        />
      </main>

      <EvidenceDrawer
        open={drawer.open}
        aspect={drawer.aspect}
        productName={drawer.productName}
        mentions={drawer.mentions}
        loading={drawer.loading}
        errorMessage={drawer.errorMessage}
        onClose={() => setDrawer((d) => ({ ...d, open: false }))}
      />
    </div>
  );
}

interface PickerColumnProps {
  company: string;
  companyOptions: SelectOption[];
  onCompanyChange: (v: string) => void;
  productId: string;
  productOptions: SelectOption[];
  onProductChange: (v: string) => void;
  disabled: boolean;
}

function PickerColumn({
  company,
  companyOptions,
  onCompanyChange,
  productId,
  productOptions,
  onProductChange,
  disabled,
}: PickerColumnProps): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Select
        label="Company"
        value={company}
        options={companyOptions}
        onChange={onCompanyChange}
        disabled={disabled}
        placeholder="Select a company"
      />
      <Select
        label="Product"
        value={productId}
        options={productOptions}
        onChange={onProductChange}
        disabled={disabled || productOptions.length === 0}
        placeholder={company ? "Select a product" : "Pick a company first"}
      />
    </div>
  );
}

interface PairBodyProps {
  pairState: PairState;
  onCellClick: (
    productName: string,
    aspect: string,
    mentionIds: string[],
  ) => void;
}

function PairBody({ pairState, onCellClick }: PairBodyProps): JSX.Element | null {
  if (pairState.kind === "idle") {
    return (
      <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-alt px-6 py-8 text-center">
        <p className="text-sm text-fg-secondary">
          Pick a product on each side to see the head-to-head comparison.
        </p>
        <p className="text-xs text-fg-muted">
          You'll see aspect-by-aspect scores, which side leads on each, and the underlying quotes behind the numbers.
        </p>
      </div>
    );
  }
  if (pairState.kind === "loading") {
    return (
      <div className="flex flex-col gap-3" aria-label="Comparing">
        <div className="flex gap-2">
          <Skeleton className="h-16 flex-1" />
          <Skeleton className="h-16 flex-1" />
          <Skeleton className="h-16 flex-1" />
        </div>
        {Array.from({ length: 6 }).map((_, idx) => (
          <Skeleton key={idx} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (pairState.kind === "error") {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-danger bg-danger-soft p-4">
        <p className="text-sm text-danger">
          Couldn't load comparison: {pairState.message}
        </p>
      </div>
    );
  }
  return <PairScorecard pair={pairState.pair} onCellClick={onCellClick} />;
}

interface PairScorecardProps {
  pair: PairResponse;
  onCellClick: (
    productName: string,
    aspect: string,
    mentionIds: string[],
  ) => void;
}

function totalMentions(row: PairAspectRow): number {
  return (
    (row.primary?.total_mentions ?? 0) +
    (row.competitor?.total_mentions ?? 0)
  );
}

function PairScorecard({ pair, onCellClick }: PairScorecardProps): JSX.Element {
  const totalAspects = pair.rows.length;
  // Sort by what gets talked about most across the two products combined —
  // operator-anchored signal of "which aspects actually matter for this
  // pairing". Tiebreaker: canonical aspect order from the backend response.
  const aspectOrder = new Map(pair.aspects.map((a, i) => [a, i]));
  const sortedRows = [...pair.rows].sort((a, b) => {
    const totalDelta = totalMentions(b) - totalMentions(a);
    if (totalDelta !== 0) return totalDelta;
    return (aspectOrder.get(a.aspect) ?? 0) - (aspectOrder.get(b.aspect) ?? 0);
  });

  return (
    <section className="flex flex-col gap-5">
      <div className="grid grid-cols-3 items-stretch gap-4">
        <CountTile
          label="LEADS"
          headline={pair.primary.display_name}
          sub={pair.primary.brand}
          count={pair.primary_leads_count}
          total={totalAspects}
        />
        <CountTile
          label="TIES"
          headline="Ties"
          sub="net sentiment within ±0.10"
          count={pair.ties_count}
          total={totalAspects}
          neutral
        />
        <CountTile
          label="LEADS"
          headline={pair.competitor.display_name}
          sub={pair.competitor.brand}
          count={pair.competitor_leads_count}
          total={totalAspects}
        />
      </div>

      <PairTable
        rows={sortedRows}
        primaryName={pair.primary.display_name}
        competitorName={pair.competitor.display_name}
        onCellClick={onCellClick}
      />

      <p className="text-xs text-fg-muted">
        Rows are sorted by how often the aspect is mentioned across both
        products combined. The highlighted side on each row is the one that
        leads (net sentiment higher by more than 0.10); ties are unhighlighted.
        Net sentiment is the share of positive minus the share of negative
        mentions, on a –1 to +1 scale. Click any cell to read the verbatim
        quotes for that side and aspect.
      </p>
    </section>
  );
}

interface CountTileProps {
  label: string;
  headline: string;
  sub: string;
  count: number;
  total: number;
  neutral?: boolean;
}

function CountTile({
  label,
  headline,
  sub,
  count,
  total,
  neutral = false,
}: CountTileProps): JSX.Element {
  const numberClass = neutral ? "text-fg-muted" : "text-accent";
  return (
    <div className="flex flex-col items-center gap-1 rounded-md border border-border bg-surface p-5 text-center shadow-card">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        {label}
      </span>
      <span className="text-sm font-medium text-fg">{headline}</span>
      <span className={`mt-1 text-3xl font-semibold tabular ${numberClass}`}>
        {count}
        <span className="text-base font-normal text-fg-muted">
          {" "}
          / {total}
        </span>
      </span>
      <span className="text-[11px] text-fg-muted">{sub}</span>
    </div>
  );
}

interface PairTableProps {
  rows: PairAspectRow[];
  primaryName: string;
  competitorName: string;
  onCellClick: (
    productName: string,
    aspect: string,
    mentionIds: string[],
  ) => void;
}

function PairTable({
  rows,
  primaryName,
  competitorName,
  onCellClick,
}: PairTableProps): JSX.Element {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-surface shadow-card">
      <div className="grid grid-cols-[1fr_220px_1fr] items-center border-b border-border bg-surface-alt px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-fg-secondary">
        <div className="text-center">{primaryName}</div>
        <div className="text-center">Aspect</div>
        <div className="text-center">{competitorName}</div>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm italic text-fg-muted">
          No aspects to compare.
        </p>
      ) : (
        rows.map((row) => (
          <PairTableRow
            key={row.aspect}
            row={row}
            primaryName={primaryName}
            competitorName={competitorName}
            onCellClick={onCellClick}
          />
        ))
      )}
    </div>
  );
}

interface PairTableRowProps {
  row: PairAspectRow;
  primaryName: string;
  competitorName: string;
  onCellClick: (
    productName: string,
    aspect: string,
    mentionIds: string[],
  ) => void;
}

function PairTableRow({
  row,
  primaryName,
  competitorName,
  onCellClick,
}: PairTableRowProps): JSX.Element {
  return (
    <div className="grid grid-cols-[1fr_220px_1fr] items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
      <div className="flex justify-center">
        <PairCellChip
          cell={row.primary}
          label={primaryName}
          aspect={row.aspect}
          leads={row.leader === "primary"}
          onClick={onCellClick}
        />
      </div>
      <div className="text-center text-sm font-medium text-fg">
        {aspectLabel(row.aspect)}
      </div>
      <div className="flex justify-center">
        <PairCellChip
          cell={row.competitor}
          label={competitorName}
          aspect={row.aspect}
          leads={row.leader === "competitor"}
          onClick={onCellClick}
        />
      </div>
    </div>
  );
}

interface PairCellChipProps {
  cell:
    | { net_sentiment: number; total_mentions: number; mention_ids: string[] }
    | null;
  label: string;
  aspect: string;
  leads: boolean;
  onClick: (productName: string, aspect: string, mentionIds: string[]) => void;
}

function PairCellChip({
  cell,
  label,
  aspect,
  leads,
  onClick,
}: PairCellChipProps): JSX.Element {
  // Leader-side gets a 2px accent ring so the eye lands on it without
  // changing the polarity tint that conveys sentiment.
  const leaderHighlight = leads
    ? "ring-2 ring-accent ring-offset-1 ring-offset-surface"
    : "";
  if (cell === null) {
    return (
      <span
        title="no mentions yet"
        className={`inline-flex items-center gap-1 rounded-sm border border-dashed border-border bg-surface-alt px-2 py-1 text-[11px] text-fg-muted ${leaderHighlight}`}
      >
        no data
      </span>
    );
  }
  const tone = netSentTone(cell.net_sentiment);
  const sign = cell.net_sentiment >= 0 ? "+" : "";
  return (
    <button
      type="button"
      onClick={() => onClick(label, aspect, cell.mention_ids)}
      title={`Click to read the ${cell.total_mentions} quote${
        cell.total_mentions === 1 ? "" : "s"
      } behind this score`}
      className={`inline-flex cursor-zoom-in items-center gap-2 rounded-sm border border-border px-2 py-1 text-xs transition-colors duration-1 ease-aw hover:brightness-95 ${netSentBg(tone)} ${leaderHighlight}`}
    >
      <span className="tabular font-medium">
        {sign}
        {cell.net_sentiment.toFixed(2)}
      </span>
      <span className="text-fg-muted">·</span>
      <span className="tabular text-fg-secondary">
        {cell.total_mentions} mention{cell.total_mentions === 1 ? "" : "s"}
      </span>
    </button>
  );
}

