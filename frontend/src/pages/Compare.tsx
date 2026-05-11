import { Link } from "react-router-dom";

/**
 * Compare — A2 pair-deliberation page placeholder (bite 11.3.b).
 *
 * Empty state only. Wave 3 builds the real surface.
 */
export function Compare(): JSX.Element {
  return (
    <main className="min-h-screen bg-surface text-fg">
      <div className="mx-auto flex min-h-screen max-w-[800px] flex-col items-center justify-center gap-6 px-8 py-14 text-center">
        <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          Compare · A2
        </span>
        <h1 className="text-2xl font-semibold text-fg">Pair deliberation</h1>
        <p className="text-sm text-fg-secondary">
          Win rates and reason buckets across resolved deliberation threads. Lands
          in Wave 3.
        </p>
        <div className="rounded-md border border-border bg-surface-alt px-6 py-4 text-sm italic text-fg-muted">
          Wave 3 — coming soon
        </div>
        <Link
          to="/"
          className="text-sm font-medium text-accent hover:text-accent-hover"
        >
          ← back to index
        </Link>
      </div>
    </main>
  );
}
