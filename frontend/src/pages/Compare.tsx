import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ApiError, api } from "@/lib/api";
import type {
  CompareCell,
  CompareProductRow,
  CompareResponse,
  MentionView,
} from "@/lib/types";

/**
 * Compare — cross-product aspect heatmap (bite 32.a).
 *
 * Rows = products (Alienware pinned top with discreet purple accent), cols =
 * the 11-aspect taxonomy in canonical order. Each cell shows the mention
 * count, tinted by polarity (success-soft / warning-soft / danger-soft per
 * DESIGN_SYSTEM §2.5). Cell click opens the EvidenceDrawer scoped to that
 * (product, aspect) tuple — same drawer the Standalone page uses, just
 * fed with a different mention_ids list.
 *
 * Auto-populate semantics: reloads `GET /api/compare` on mount only. As
 * Stage B's aggregation step writes new rows, the operator gets the updated
 * grid by refreshing the tab — no polling.
 */

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: CompareResponse };

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

// Short labels for the 11-aspect column headers so they fit ~80px columns at
// 1280px desktop minimum. Fallback echoes the raw aspect string if a new key
// lands without a label entry.
const ASPECT_LABELS: Record<string, string> = {
  thermals: "Thermals",
  performance: "Performance",
  keyboard: "Keyboard",
  display: "Display",
  battery: "Battery",
  build_quality: "Build",
  software_experience: "Software",
  price_value: "Price/Value",
  support_warranty: "Support",
  aesthetics: "Aesthetics",
  portability: "Portability",
};

function aspectLabel(aspect: string): string {
  return ASPECT_LABELS[aspect] ?? aspect;
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

type CellTone = "pos" | "neg" | "neu";

function cellTone(net: number): CellTone {
  if (net > 0.15) return "pos";
  if (net < -0.15) return "neg";
  return "neu";
}

function cellBgClass(tone: CellTone): string {
  if (tone === "pos") return "bg-success-soft";
  if (tone === "neg") return "bg-danger-soft";
  return "bg-warning-soft";
}

// 130px company column + 200px product column + 11 aspect columns that flex
// to fill remaining width. `min-w-[1240px]` on the inner grid forces
// horizontal scroll below ~1280px once the company col is in.
const GRID_TEMPLATE =
  "grid-cols-[130px_200px_repeat(11,minmax(72px,1fr))]";

// Screen-size buckets the size filter offers. Derived from the digit after
// the model name in `display_name` ("Alienware 16 Aurora" → "16").
const SCREEN_SIZE_PATTERN = /\b(13|14|15|16|17|18)\b/;

function deriveScreenSize(displayName: string): string | null {
  const match = displayName.match(SCREEN_SIZE_PATTERN);
  return match ? match[1] : null;
}

interface HeatCellProps {
  cell: CompareCell | undefined;
  onClick: () => void;
}

function HeatCell({ cell, onClick }: HeatCellProps): JSX.Element {
  if (!cell || cell.total_mentions === 0) {
    return (
      <div
        aria-hidden="true"
        className="flex h-9 items-center justify-center border-r border-b border-border bg-surface-alt"
        title="no data yet"
      >
        <span className="text-[10px] text-fg-muted">—</span>
      </div>
    );
  }
  const tone = cellTone(cell.net_sentiment);
  const sign = cell.net_sentiment >= 0 ? "+" : "";
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${cell.aspect} · net ${sign}${cell.net_sentiment.toFixed(2)} · ${cell.total_mentions} mention${cell.total_mentions === 1 ? "" : "s"}`}
      className={`flex h-9 cursor-zoom-in items-center justify-end border-r border-b border-border px-2 transition-colors duration-1 ease-aw hover:brightness-95 ${cellBgClass(tone)}`}
    >
      <span className="tabular text-[11px] font-medium text-fg-secondary">
        {cell.total_mentions}
      </span>
    </button>
  );
}

interface ProductRowProps {
  row: CompareProductRow;
  aspects: string[];
  onCellClick: (row: CompareProductRow, cell: CompareCell) => void;
}

interface FilterPanelProps {
  allCompanies: string[];
  allSizes: string[];
  allProducts: CompareProductRow[];
  selectedCompanies: Set<string>;
  selectedSizes: Set<string>;
  selectedProducts: Set<string>;
  productPickerOpen: boolean;
  onToggleCompany: (c: string) => void;
  onToggleSize: (s: string) => void;
  onToggleProduct: (p: string) => void;
  onClearCompanies: () => void;
  onClearSizes: () => void;
  onClearProducts: () => void;
  onToggleProductPicker: () => void;
  shownCount: number;
  totalCount: number;
}

function FilterPanel({
  allCompanies,
  allSizes,
  allProducts,
  selectedCompanies,
  selectedSizes,
  selectedProducts,
  productPickerOpen,
  onToggleCompany,
  onToggleSize,
  onToggleProduct,
  onClearCompanies,
  onClearSizes,
  onClearProducts,
  onToggleProductPicker,
  shownCount,
  totalCount,
}: FilterPanelProps): JSX.Element {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4 shadow-card">
      <FilterRow
        label="Company"
        items={allCompanies}
        selected={selectedCompanies}
        onToggle={onToggleCompany}
        onClear={onClearCompanies}
      />
      <FilterRow
        label="Screen size"
        items={allSizes.map((s) => `${s}"`)}
        rawItems={allSizes}
        selected={selectedSizes}
        onToggle={onToggleSize}
        onClear={onClearSizes}
      />
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onToggleProductPicker}
            className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-fg-secondary hover:text-accent"
          >
            <span
              aria-hidden="true"
              className="inline-block text-[10px]"
              style={{
                transform: productPickerOpen
                  ? "rotate(90deg)"
                  : "rotate(0deg)",
              }}
            >
              ▶
            </span>
            Product
          </button>
          <span className="text-xs text-fg-muted">
            {selectedProducts.size > 0
              ? `${selectedProducts.size} selected`
              : "(all)"}
          </span>
          {selectedProducts.size > 0 && (
            <button
              type="button"
              onClick={onClearProducts}
              className="text-xs font-medium text-accent hover:text-accent-hover"
            >
              clear
            </button>
          )}
        </div>
        {productPickerOpen && (
          <div className="flex flex-wrap gap-1.5">
            {allProducts.map((p) => (
              <FilterChip
                key={p.product_id}
                label={p.display_name}
                selected={selectedProducts.has(p.product_id)}
                onClick={() => onToggleProduct(p.product_id)}
              />
            ))}
          </div>
        )}
      </div>
      <p className="text-xs text-fg-muted">
        Showing <span className="font-medium text-fg">{shownCount}</span> of{" "}
        {totalCount} products.
      </p>
    </div>
  );
}

interface FilterRowProps {
  label: string;
  items: string[];
  rawItems?: string[]; // when display label differs from the toggle key
  selected: Set<string>;
  onToggle: (key: string) => void;
  onClear: () => void;
}

function FilterRow({
  label,
  items,
  rawItems,
  selected,
  onToggle,
  onClear,
}: FilterRowProps): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-secondary">
        {label}
      </span>
      {items.map((display, i) => {
        const key = rawItems ? rawItems[i] : display;
        return (
          <FilterChip
            key={key}
            label={display}
            selected={selected.has(key)}
            onClick={() => onToggle(key)}
          />
        );
      })}
      {selected.size > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="ml-1 text-xs font-medium text-accent hover:text-accent-hover"
        >
          clear
        </button>
      )}
    </div>
  );
}

interface FilterChipProps {
  label: string;
  selected: boolean;
  onClick: () => void;
}

function FilterChip({ label, selected, onClick }: FilterChipProps): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-sm border px-2 py-0.5 text-xs transition-colors duration-1 ease-aw ${
        selected
          ? "border-accent bg-accent-soft font-medium text-accent-hover"
          : "border-border bg-surface text-fg-secondary hover:border-accent hover:text-accent"
      }`}
    >
      {label}
    </button>
  );
}

interface ProductRowExtraProps extends ProductRowProps {
  brandLabel: string | null; // null = same brand as the row above; render empty
}

function ProductRow({
  row,
  aspects,
  brandLabel,
  onCellClick,
}: ProductRowExtraProps): JSX.Element {
  const cellByAspect = new Map(row.cells.map((c) => [c.aspect, c]));
  const isAlienware = row.brand.toLowerCase().startsWith("alienware");
  // Purple 2px left edge on Alienware rows; the rest get a 2px transparent
  // edge so the grid stays optically aligned.
  const productCellBorder = isAlienware
    ? "border-l-2 border-l-accent"
    : "border-l-2 border-l-transparent";
  // First row of each brand carries a subtle top divider so brand groups
  // read as visually separated bands.
  const brandStart = brandLabel !== null;
  const topBorder = brandStart ? "border-t border-border" : "";
  return (
    <>
      <div
        className={`sticky left-[0px] z-10 flex h-9 items-center border-r border-b border-border bg-surface-alt px-3 ${topBorder}`}
      >
        {brandLabel && (
          <span className="truncate text-[11px] font-semibold uppercase tracking-wide text-fg-secondary">
            {brandLabel}
          </span>
        )}
      </div>
      <Link
        to={`/standalone/${row.product_id}`}
        className={`sticky left-[130px] z-10 flex h-9 min-w-0 items-center gap-2 border-r border-b border-border bg-surface px-3 hover:bg-surface-alt ${productCellBorder} ${topBorder}`}
        title={`open ${row.display_name}`}
      >
        <span className="truncate text-xs font-medium text-fg">
          {row.display_name}
        </span>
      </Link>
      {aspects.map((aspect) => (
        <div key={aspect} className={topBorder}>
          <HeatCell
            cell={cellByAspect.get(aspect)}
            onClick={() => {
              const c = cellByAspect.get(aspect);
              if (c) onCellClick(row, c);
            }}
          />
        </div>
      ))}
    </>
  );
}

export function Compare(): JSX.Element {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [drawer, setDrawer] = useState<DrawerState>(INITIAL_DRAWER);
  const [selectedCompanies, setSelectedCompanies] = useState<Set<string>>(
    new Set(),
  );
  const [selectedSizes, setSelectedSizes] = useState<Set<string>>(new Set());
  const [selectedProducts, setSelectedProducts] = useState<Set<string>>(
    new Set(),
  );
  const [productPickerOpen, setProductPickerOpen] = useState(false);

  const toggleInSet = <T,>(
    setter: (next: Set<T>) => void,
    current: Set<T>,
    key: T,
  ): void => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setter(next);
  };

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .compare()
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ready", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const allCompanies = useMemo<string[]>(() => {
    if (state.kind !== "ready") return [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const p of state.data.products) {
      if (!seen.has(p.brand)) {
        seen.add(p.brand);
        out.push(p.brand);
      }
    }
    return out;
  }, [state]);

  const allSizes = useMemo<string[]>(() => {
    if (state.kind !== "ready") return [];
    const seen = new Set<string>();
    for (const p of state.data.products) {
      const s = deriveScreenSize(p.display_name);
      if (s) seen.add(s);
    }
    return [...seen].sort();
  }, [state]);

  const filteredProducts = useMemo<CompareProductRow[]>(() => {
    if (state.kind !== "ready") return [];
    return state.data.products.filter((p) => {
      if (selectedCompanies.size > 0 && !selectedCompanies.has(p.brand))
        return false;
      if (selectedProducts.size > 0 && !selectedProducts.has(p.product_id))
        return false;
      if (selectedSizes.size > 0) {
        const s = deriveScreenSize(p.display_name);
        if (!s || !selectedSizes.has(s)) return false;
      }
      return true;
    });
  }, [state, selectedCompanies, selectedProducts, selectedSizes]);

  const onCellClick = useCallback(
    (row: CompareProductRow, cell: CompareCell): void => {
      setDrawer({
        open: true,
        aspect: cell.aspect,
        productName: row.display_name,
        loading: true,
        mentions: [],
        errorMessage: null,
      });
      api
        .mentions(cell.mention_ids)
        .then((res) => {
          setDrawer((prev) =>
            prev.open &&
            prev.aspect === cell.aspect &&
            prev.productName === row.display_name
              ? { ...prev, loading: false, mentions: res.mentions }
              : prev,
          );
        })
        .catch((err: unknown) => {
          setDrawer((prev) =>
            prev.open &&
            prev.aspect === cell.aspect &&
            prev.productName === row.display_name
              ? { ...prev, loading: false, errorMessage: describeError(err) }
              : prev,
          );
        });
    },
    [],
  );

  return (
    <div className="min-h-screen bg-surface text-fg">
      <main className="mx-auto flex max-w-[1400px] flex-col gap-6 px-8 py-8">
        <header className="flex flex-col gap-1">
          <Link
            to="/"
            className="self-start text-xs font-medium text-accent hover:text-accent-hover"
          >
            ← back
          </Link>
          <span className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
            Compare · cross-product
          </span>
          <h1 className="text-xl font-semibold text-fg">
            Aspect heatmap — gaming laptops
          </h1>
          {state.kind === "ready" && (
            <p className="text-xs text-fg-muted">
              run · {state.data.run_id ?? "(no run with data)"} ·{" "}
              {state.data.products.length} product
              {state.data.products.length === 1 ? "" : "s"}
            </p>
          )}
        </header>

        {state.kind === "loading" && (
          <p className="text-sm text-fg-muted">Loading heatmap…</p>
        )}

        {state.kind === "error" && (
          <div className="flex flex-col gap-2 rounded-md border border-danger bg-danger-soft p-4">
            <p className="text-sm text-danger">
              Couldn't load comparison: {state.message}
            </p>
            <button
              type="button"
              onClick={() => setReloadKey((k) => k + 1)}
              className="self-start text-xs font-medium text-accent hover:text-accent-hover"
            >
              retry
            </button>
          </div>
        )}

        {state.kind === "ready" && state.data.products.length === 0 && (
          <p className="text-sm italic text-fg-muted">
            No products in the latest run. Seed the DB or run the pipeline first.
          </p>
        )}

        {state.kind === "ready" && state.data.products.length > 0 && (
          <section className="flex flex-col gap-3">
            <FilterPanel
              allCompanies={allCompanies}
              allSizes={allSizes}
              allProducts={state.data.products}
              selectedCompanies={selectedCompanies}
              selectedSizes={selectedSizes}
              selectedProducts={selectedProducts}
              productPickerOpen={productPickerOpen}
              onToggleCompany={(c) =>
                toggleInSet(setSelectedCompanies, selectedCompanies, c)
              }
              onToggleSize={(s) =>
                toggleInSet(setSelectedSizes, selectedSizes, s)
              }
              onToggleProduct={(p) =>
                toggleInSet(setSelectedProducts, selectedProducts, p)
              }
              onClearCompanies={() => setSelectedCompanies(new Set())}
              onClearSizes={() => setSelectedSizes(new Set())}
              onClearProducts={() => setSelectedProducts(new Set())}
              onToggleProductPicker={() =>
                setProductPickerOpen((v) => !v)
              }
              shownCount={filteredProducts.length}
              totalCount={state.data.products.length}
            />

            {filteredProducts.length === 0 ? (
              <p className="rounded-md border border-border bg-surface-alt p-4 text-sm italic text-fg-muted">
                No products match the current filters.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border border-border bg-surface shadow-card">
                <div className={`grid ${GRID_TEMPLATE} min-w-[1240px]`}>
                  {/* sticky header row */}
                  <div className="sticky top-0 left-0 z-30 flex h-9 items-center border-r border-b border-border bg-surface-alt px-3 text-[11px] font-semibold uppercase tracking-wide text-fg-secondary">
                    company
                  </div>
                  <div className="sticky top-0 left-[130px] z-30 flex h-9 items-center border-r border-b border-border bg-surface-alt px-3 text-[11px] font-semibold uppercase tracking-wide text-fg-secondary">
                    product
                  </div>
                  {state.data.aspects.map((a) => (
                    <div
                      key={a}
                      className="sticky top-0 z-20 flex h-9 items-center justify-center border-r border-b border-border bg-surface-alt px-2 text-center text-[11px] font-semibold tracking-wide text-fg-secondary"
                      title={a}
                    >
                      {aspectLabel(a)}
                    </div>
                  ))}

                  {/* product rows — brandLabel populated on the first row of
                      each brand group so the company column reads as a banner */}
                  {filteredProducts.map((row, idx) => {
                    const prevBrand =
                      idx === 0 ? null : filteredProducts[idx - 1].brand;
                    const brandLabel =
                      row.brand !== prevBrand ? row.brand : null;
                    return (
                      <ProductRow
                        key={row.product_id}
                        row={row}
                        aspects={state.data.aspects}
                        brandLabel={brandLabel}
                        onCellClick={onCellClick}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            <p className="text-xs text-fg-muted">
              Green = positive sentiment, yellow = mixed/neutral, red = negative.
              The number is the mention count for that (product, aspect). Click
              any cell to drill into verbatims. Empty cells mean no tagged
              mentions yet. Alienware rows are marked with a purple edge.
            </p>
          </section>
        )}
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
