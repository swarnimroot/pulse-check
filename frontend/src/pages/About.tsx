import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Select, type SelectOption } from "@/components/atoms";
import { ApiError, api } from "@/lib/api";
import type { ProductSummary } from "@/lib/types";

/**
 * About — index page (bite 11.3.c live wiring).
 *
 * Header + Standalone selector card (Company → Product → Open) + Compare
 * placeholder. Fetches `/api/products` on mount; selectors are populated
 * from the live response, grouped by `brand` (the only grouping dimension
 * the schema exposes — "Company" in DESIGN_SYSTEM §6.1 maps to `brand`
 * field; rename if a true company hierarchy lands).
 */

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; products: ProductSummary[] };

export function About(): JSX.Element {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [company, setCompany] = useState<string>("");
  const [productId, setProductId] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .products()
      .then((res) => {
        if (cancelled) return;
        setState({ kind: "ready", products: res.products });
        // Auto-select the first company + its first product so the operator
        // can hit "Open" without manually picking when only one company exists.
        if (res.products.length > 0) {
          const first = res.products[0];
          setCompany(first.brand);
          setProductId(first.product_id);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Failed to load products.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const companyOptions = useMemo<SelectOption[]>(() => {
    if (state.kind !== "ready") return [];
    const seen = new Set<string>();
    const unique: SelectOption[] = [];
    for (const p of state.products) {
      if (!seen.has(p.brand)) {
        seen.add(p.brand);
        unique.push({ value: p.brand, label: p.brand });
      }
    }
    return unique;
  }, [state]);

  const productOptions = useMemo<SelectOption[]>(() => {
    if (state.kind !== "ready" || company === "") return [];
    return state.products
      .filter((p) => p.brand === company)
      .map((p) => ({ value: p.product_id, label: p.display_name }));
  }, [state, company]);

  const handleCompanyChange = (next: string): void => {
    setCompany(next);
    // Reset product selection to the first product under the new company.
    if (state.kind === "ready") {
      const firstInCompany = state.products.find((p) => p.brand === next);
      setProductId(firstInCompany?.product_id ?? "");
    } else {
      setProductId("");
    }
  };

  return (
    <main className="min-h-screen bg-surface text-fg">
      <div className="mx-auto flex max-w-[1100px] flex-col gap-10 px-8 py-14">
        <header className="flex flex-col gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
            pulse-check
          </span>
          <h1 className="text-2xl font-semibold text-fg">
            Product listening — internal pilot
          </h1>
          <p className="text-sm text-fg-secondary">
            Standalone product voice (A1) and comparative deliberation (A2). Two
            aspects, one operator surface.
          </p>
        </header>

        <section className="grid grid-cols-2 gap-6">
          <article className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6 shadow-card">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
                Standalone · A1
              </span>
              <h2 className="text-base font-semibold text-fg">
                Standalone — single product voice
              </h2>
              <p className="text-sm text-fg-secondary">
                Per-product scorecard across 11 aspects, anchored to mention-ID
                provenance.
              </p>
            </div>

            {state.kind === "loading" && (
              <p className="text-sm text-fg-muted">Loading…</p>
            )}

            {state.kind === "error" && (
              <div className="flex flex-col gap-2 rounded-sm border border-danger bg-danger-soft p-3">
                <p className="text-sm text-danger">
                  Couldn't load products: {state.message}
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

            {state.kind === "ready" && state.products.length === 0 && (
              <p className="text-sm italic text-fg-muted">
                No products in the latest run. Seed the DB or run the pipeline first.
              </p>
            )}

            {state.kind === "ready" && state.products.length > 0 && (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <Select
                    label="Company"
                    value={company}
                    options={companyOptions}
                    onChange={handleCompanyChange}
                  />
                  <Select
                    label="Product"
                    value={productId}
                    options={productOptions}
                    onChange={setProductId}
                    disabled={productOptions.length === 0}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/standalone/${productId}`)}
                  disabled={productId === ""}
                  className="self-start rounded-sm bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-alt disabled:text-fg-muted"
                >
                  Open standalone →
                </button>
              </div>
            )}
          </article>

          <article className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6 shadow-card">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
                Compare · A2
              </span>
              <h2 className="text-base font-semibold text-fg">
                Compare — pair deliberation
              </h2>
              <p className="text-sm text-fg-secondary">
                Win-rate + reason buckets per pair from resolved deliberation
                threads.
              </p>
            </div>
            <Link
              to="/compare"
              className="text-sm font-medium text-accent hover:text-accent-hover"
            >
              View placeholder →
            </Link>
            <p className="text-xs italic text-fg-muted">Wave 3 — coming soon</p>
          </article>
        </section>

        <div className="mt-2">
          <Link
            to="/showcase"
            className="text-xs font-medium text-fg-muted hover:text-accent"
          >
            design system showcase →
          </Link>
        </div>
      </div>
    </main>
  );
}
