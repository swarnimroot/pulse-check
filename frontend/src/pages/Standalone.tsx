import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AspectColumn } from "@/components/AspectColumn";
import { BriefPanel } from "@/components/BriefPanel";
import { CitationPanel } from "@/components/CitationPanel";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { RunMetaStrip } from "@/components/RunMetaStrip";
import { Select, type SelectOption } from "@/components/atoms";
import { GlossaryButton } from "@/components/GlossaryDialog";
import { BriefExportButton } from "@/components/BriefExportButton";
import { ApiError, api } from "@/lib/api";
import type {
  BriefView,
  MentionView,
  ProductDetail,
  ProductSummary,
} from "@/lib/types";

/**
 * Standalone — A1 single-product voice page (bite 11.3.c live-wired).
 *
 * Reads `:productId` from the URL, fetches `/api/product/:id`, follows
 * `latest_brief_id` to `/api/brief/:id`, lazy-fetches mentions on drawer /
 * citation open. 404 → not-found card.
 */

type ProductState =
  | { kind: "loading" }
  | { kind: "notFound" }
  | { kind: "error"; message: string }
  | { kind: "ready"; product: ProductDetail };

type BriefState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "missing" }
  | { kind: "ready"; brief: BriefView };

interface DrawerState {
  open: boolean;
  aspect: string;
  loading: boolean;
  mentions: MentionView[];
  errorMessage: string | null;
}

interface PanelState {
  open: boolean;
  claimText: string;
  loading: boolean;
  mentions: MentionView[];
  errorMessage: string | null;
}

const INITIAL_DRAWER: DrawerState = {
  open: false,
  aspect: "",
  loading: false,
  mentions: [],
  errorMessage: null,
};

const INITIAL_PANEL: PanelState = {
  open: false,
  claimText: "",
  loading: false,
  mentions: [],
  errorMessage: null,
};

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

export function Standalone(): JSX.Element {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();

  // All hooks declared above any early return so rules-of-hooks holds even
  // through the not-found branch.
  const [productState, setProductState] = useState<ProductState>({ kind: "loading" });
  const [briefState, setBriefState] = useState<BriefState>({ kind: "idle" });
  const [productReloadKey, setProductReloadKey] = useState(0);
  const [drawer, setDrawer] = useState<DrawerState>(INITIAL_DRAWER);
  const [panel, setPanel] = useState<PanelState>(INITIAL_PANEL);
  const [allProducts, setAllProducts] = useState<ProductSummary[]>([]);
  const [pickerCompany, setPickerCompany] = useState<string>("");

  // Load the full product list once for the company/product pickers.
  useEffect(() => {
    let cancelled = false;
    api
      .products()
      .then((res) => {
        if (cancelled) return;
        setAllProducts(res.products);
      })
      .catch(() => {
        // Picker is non-essential; fall back to no picker if products fetch
        // fails. The main product detail fetch already surfaces its own error.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sync the picker's company state to the currently-viewed product's brand
  // whenever the URL product or the product list changes.
  useEffect(() => {
    if (!productId || allProducts.length === 0) return;
    const current = allProducts.find((p) => p.product_id === productId);
    if (current) setPickerCompany(current.brand);
  }, [productId, allProducts]);

  // Product fetch. Resets on productId change or manual retry. Empty
  // productId is the "no selection yet" landing state — render just the
  // picker (handled below) rather than a 404.
  useEffect(() => {
    if (!productId) {
      setProductState({ kind: "loading" });
      return;
    }
    let cancelled = false;
    setProductState({ kind: "loading" });
    setBriefState({ kind: "idle" });
    api
      .productById(productId)
      .then((product) => {
        if (cancelled) return;
        setProductState({ kind: "ready", product });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === 404) {
          setProductState({ kind: "notFound" });
          return;
        }
        setProductState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [productId, productReloadKey]);

  // Brief fetch — fires only when product is ready and advertises a brief.
  useEffect(() => {
    if (productState.kind !== "ready") return;
    const briefId = productState.product.latest_brief_id;
    if (briefId === null) {
      setBriefState({ kind: "missing" });
      return;
    }
    let cancelled = false;
    setBriefState({ kind: "loading" });
    api
      .brief(briefId)
      .then((brief) => {
        if (cancelled) return;
        setBriefState({ kind: "ready", brief });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setBriefState({ kind: "error", message: describeError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [productState]);

  const openDrawer = useCallback((aspect: string, ids: string[]): void => {
    setDrawer({
      open: true,
      aspect,
      loading: true,
      mentions: [],
      errorMessage: null,
    });
    api
      .mentions(ids)
      .then((res) => {
        setDrawer((prev) =>
          prev.open && prev.aspect === aspect
            ? { ...prev, loading: false, mentions: res.mentions }
            : prev,
        );
      })
      .catch((err: unknown) => {
        setDrawer((prev) =>
          prev.open && prev.aspect === aspect
            ? { ...prev, loading: false, errorMessage: describeError(err) }
            : prev,
        );
      });
  }, []);

  const companyOptions = useMemo<SelectOption[]>(() => {
    const seen = new Set<string>();
    const out: SelectOption[] = [];
    for (const p of allProducts) {
      if (!seen.has(p.brand)) {
        seen.add(p.brand);
        out.push({ value: p.brand, label: p.brand });
      }
    }
    return out;
  }, [allProducts]);

  const productOptions = useMemo<SelectOption[]>(() => {
    if (!pickerCompany) return [];
    return allProducts
      .filter((p) => p.brand === pickerCompany)
      .map((p) => ({ value: p.product_id, label: p.display_name }));
  }, [allProducts, pickerCompany]);

  const handlePickerCompanyChange = (next: string): void => {
    setPickerCompany(next);
    // No auto-jump: the operator explicitly picks the product on the next
    // dropdown. Keeps the URL pointing at the previous product (or empty)
    // until the second pick lands.
  };

  const handlePickerProductChange = (nextId: string): void => {
    if (!nextId || nextId === productId) return;
    navigate(`/standalone/${nextId}`);
  };

  const openCitation = useCallback(
    (claimText: string, citedMentionIds: string[]): void => {
      setPanel({
        open: true,
        claimText,
        loading: true,
        mentions: [],
        errorMessage: null,
      });
      api
        .mentions(citedMentionIds)
        .then((res) => {
          setPanel((prev) =>
            prev.open && prev.claimText === claimText
              ? { ...prev, loading: false, mentions: res.mentions }
              : prev,
          );
        })
        .catch((err: unknown) => {
          setPanel((prev) =>
            prev.open && prev.claimText === claimText
              ? { ...prev, loading: false, errorMessage: describeError(err) }
              : prev,
          );
        });
    },
    [],
  );

  // Empty-state landing: no productId in the URL. Show only the picker so
  // the visitor explicitly chooses both Company and Product before any
  // content renders.
  if (!productId) {
    return (
      <main className="min-h-screen bg-surface text-fg">
        <div className="mx-auto flex max-w-[800px] flex-col gap-8 px-8 py-14">
          <header className="flex items-start justify-between gap-6">
            <div className="flex flex-col gap-1">
              <Link
                to="/"
                className="self-start text-xs font-medium text-accent hover:text-accent-hover"
              >
                ← back
              </Link>
              <span className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
                Standalone · A1 voice
              </span>
              <h1 className="text-xl font-semibold text-fg">
                Pick a product to view
              </h1>
              <p className="max-w-[560px] text-sm text-fg-secondary">
                Select a company, then a product. The scorecard and brief load
                once both are chosen.
              </p>
            </div>
            <GlossaryButton />
          </header>
          {allProducts.length > 0 ? (
            <section className="flex flex-col gap-3 rounded-md border border-border bg-surface p-5 shadow-card">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
                Choose a product
              </span>
              <div className="grid grid-cols-2 gap-3">
                <Select
                  label="Company"
                  value={pickerCompany}
                  options={companyOptions}
                  onChange={handlePickerCompanyChange}
                  placeholder="Select a company"
                />
                <Select
                  label="Product"
                  value=""
                  options={productOptions}
                  onChange={handlePickerProductChange}
                  disabled={productOptions.length === 0}
                  placeholder={
                    pickerCompany ? "Select a product" : "Pick a company first"
                  }
                />
              </div>
            </section>
          ) : (
            <p className="text-sm text-fg-muted">Loading products…</p>
          )}
        </div>
      </main>
    );
  }

  if (productState.kind === "loading") {
    return (
      <main className="min-h-screen bg-surface text-fg">
        <div className="mx-auto flex min-h-screen max-w-[800px] flex-col items-center justify-center px-8 text-center">
          <p className="text-sm text-fg-muted">Loading product…</p>
        </div>
      </main>
    );
  }

  if (productState.kind === "notFound") {
    return (
      <main className="min-h-screen bg-surface text-fg">
        <div className="mx-auto flex min-h-screen max-w-[800px] flex-col items-center justify-center gap-6 px-8 py-14 text-center">
          <article className="flex w-full flex-col gap-3 rounded-md border border-border bg-surface p-6 shadow-card">
            <h1 className="text-base font-semibold text-fg">Product not found</h1>
            <p className="text-sm text-fg-secondary">
              No product matches{" "}
              <code className="rounded bg-surface-alt px-1.5 py-0.5 text-xs text-fg">
                {productId ?? "(missing id)"}
              </code>
              .
            </p>
            <Link
              to="/"
              className="self-start text-sm font-medium text-accent hover:text-accent-hover"
            >
              return to index →
            </Link>
          </article>
        </div>
      </main>
    );
  }

  if (productState.kind === "error") {
    return (
      <main className="min-h-screen bg-surface text-fg">
        <div className="mx-auto flex min-h-screen max-w-[800px] flex-col items-center justify-center gap-6 px-8 py-14 text-center">
          <article className="flex w-full flex-col gap-3 rounded-md border border-danger bg-danger-soft p-6">
            <h1 className="text-base font-semibold text-danger">
              Couldn't load product
            </h1>
            <p className="text-sm text-fg-secondary">{productState.message}</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setProductReloadKey((k) => k + 1)}
                className="self-start text-sm font-medium text-accent hover:text-accent-hover"
              >
                retry
              </button>
              <Link
                to="/"
                className="self-start text-sm font-medium text-fg-muted hover:text-accent"
              >
                return to index →
              </Link>
            </div>
          </article>
        </div>
      </main>
    );
  }

  const product = productState.product;

  return (
    <div className="min-h-screen bg-surface text-fg">
      <RunMetaStrip
        totalMentions={product.run_meta.total_mentions}
        windowLabel={product.run_meta.window_label}
        lastRefreshed={product.run_meta.last_refreshed}
      />

      <main className="mx-auto flex max-w-[1200px] flex-col gap-10 px-8 py-10">
        <header className="flex items-start justify-between gap-6">
          <div className="flex flex-col gap-1">
            <Link
              to="/"
              className="self-start text-xs font-medium text-accent hover:text-accent-hover"
            >
              ← back
            </Link>
            <span className="mt-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
              Standalone · A1 voice
            </span>
            <h1 className="text-xl font-semibold text-fg">{product.display_name}</h1>
          </div>
          <div className="flex items-start gap-2">
            <GlossaryButton />
            {briefState.kind === "ready" && (
              <BriefExportButton brief={briefState.brief} product={product} />
            )}
          </div>
        </header>

        {allProducts.length > 0 && (
          <section className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4 shadow-card">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
              Pick a different product
            </span>
            <div className="grid grid-cols-2 gap-3">
              <Select
                label="Company"
                value={pickerCompany}
                options={companyOptions}
                onChange={handlePickerCompanyChange}
              />
              <Select
                label="Product"
                value={productId ?? ""}
                options={productOptions}
                onChange={handlePickerProductChange}
                disabled={productOptions.length === 0}
              />
            </div>
          </section>
        )}

        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">{product.display_name} — aspect summary</h2>
          <div className="grid grid-cols-2 gap-4">
            <AspectColumn
              title="What's working"
              polarity="positive"
              rows={product.aspects}
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
              rows={product.aspects}
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
            Secondary (top-3 by secondary mentions, deduped against Primary), and
            Long-tail. The bucket chip on each row names which bucket the metrics
            belong to.
          </p>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-md text-fg">a1 brief</h2>
          {briefState.kind === "loading" && (
            <p className="text-sm text-fg-muted">Loading brief…</p>
          )}
          {briefState.kind === "missing" && (
            <p className="text-sm italic text-fg-muted">
              No A1 brief generated for this product yet.
            </p>
          )}
          {briefState.kind === "error" && (
            <div className="flex flex-col gap-2 rounded-md border border-danger bg-danger-soft p-4">
              <p className="text-sm text-danger">
                Couldn't load brief: {briefState.message}
              </p>
              <button
                type="button"
                onClick={() => {
                  if (productState.kind !== "ready") return;
                  // Re-trigger the brief effect by bumping the product reload key.
                  setProductReloadKey((k) => k + 1);
                }}
                className="self-start text-xs font-medium text-accent hover:text-accent-hover"
              >
                retry
              </button>
            </div>
          )}
          {briefState.kind === "ready" && (
            <BriefPanel
              narrative={briefState.brief.narrative}
              model={briefState.brief.model}
              promptVersion={briefState.brief.prompt_version}
              onCite={openCitation}
            />
          )}
        </section>
      </main>

      <EvidenceDrawer
        open={drawer.open}
        aspect={drawer.aspect}
        productName={product.display_name}
        mentions={drawer.mentions}
        loading={drawer.loading}
        errorMessage={drawer.errorMessage}
        onClose={() => setDrawer((d) => ({ ...d, open: false }))}
      />
      <CitationPanel
        open={panel.open}
        claimText={panel.claimText}
        mentions={panel.mentions}
        loading={panel.loading}
        errorMessage={panel.errorMessage}
        offsetForDrawer={drawer.open}
        onClose={() => setPanel((p) => ({ ...p, open: false }))}
      />
    </div>
  );
}
