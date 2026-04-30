import { Link, useParams } from "react-router-dom";

/** A1 product scorecard — shell only. Full implementation in Wave 2. */
export function Product(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  return (
    <main className="min-h-screen bg-surface-0 text-text-primary">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-8 py-12">
        <Link
          to="/"
          className="text-label uppercase tracking-wider text-text-tertiary hover:text-accent"
        >
          ← back
        </Link>
        <header className="flex flex-col gap-2">
          <p className="text-label uppercase tracking-wider text-text-tertiary">A1 scorecard</p>
          <h1 className="font-display text-display text-text-primary">
            product <span className="text-accent">{id ?? "—"}</span>
          </h1>
          <p className="text-body text-text-secondary">
            Empty Wave 1 shell. AspectRow × 11 + BriefPanel populate here in Wave 2.
          </p>
        </header>
      </div>
    </main>
  );
}
