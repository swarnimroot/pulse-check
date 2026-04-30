import { Link } from "react-router-dom";

/**
 * Landing — A1 / A2 selector (full implementation in Wave 2 / Wave 3).
 *
 * Wave 1 renders an empty themed shell that exercises the design tokens and
 * route targets: operator can click through to `/product/:id` and `/pair/:id`
 * via the demo links to confirm routing + theming render correctly.
 */
export function Landing(): JSX.Element {
  return (
    <main className="min-h-screen bg-surface-0 text-text-primary">
      <div className="mx-auto flex max-w-5xl flex-col gap-8 px-8 py-16">
        <header className="flex flex-col gap-2">
          <p className="text-label uppercase tracking-wider text-text-tertiary">pulse-check</p>
          <h1 className="font-display text-display text-text-primary">
            Product listening — standalone voice & comparative deliberation
          </h1>
          <p className="text-body text-text-secondary">
            Wave 1 shell. A1 product scorecards and A2 pair views will land here.
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-2">
          <article className="rounded-md border border-border-subtle bg-surface-1 p-6 shadow-card">
            <h2 className="font-display text-h2 text-text-primary">A1 — Standalone voice</h2>
            <p className="mt-2 text-body text-text-secondary">
              Per-product scorecard across 11 aspects.
            </p>
            <Link
              to="/product/demo"
              className="mt-6 inline-flex items-center text-body font-semibold text-accent hover:text-accent-hover"
            >
              Open product demo route →
            </Link>
          </article>

          <article className="rounded-md border border-border-subtle bg-surface-1 p-6 shadow-card">
            <h2 className="font-display text-h2 text-text-primary">A2 — Comparative deliberation</h2>
            <p className="mt-2 text-body text-text-secondary">
              Per-pair win rate, reason buckets, addressability.
            </p>
            <Link
              to="/pair/demo"
              className="mt-6 inline-flex items-center text-body font-semibold text-accent hover:text-accent-hover"
            >
              Open pair demo route →
            </Link>
          </article>
        </section>
      </div>
    </main>
  );
}
