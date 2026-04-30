import { Link, useParams } from "react-router-dom";

/** A2 pair view — shell only. Full implementation in Wave 3. */
export function Pair(): JSX.Element {
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
          <p className="text-label uppercase tracking-wider text-text-tertiary">A2 pair view</p>
          <h1 className="font-display text-display text-text-primary">
            pair <span className="text-accent">{id ?? "—"}</span>
          </h1>
          <p className="text-body text-text-secondary">
            Empty Wave 1 shell. WinRateHeader + ReasonRow grid + BriefPanel populate here in Wave 3.
          </p>
        </header>
      </div>
    </main>
  );
}
