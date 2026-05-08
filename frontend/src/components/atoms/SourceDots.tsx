import { cn } from "@/lib/utils";

/**
 * SourceDots — five fixed-order dots showing which sources have any mention
 * for this aspect bucket. Used in expanded AspectRow only.
 */

const ORDER = ["reddit", "bestbuy", "amazon", "youtube", "article"] as const;

function normalize(sourceType: string): (typeof ORDER)[number] | null {
  const s = sourceType.toLowerCase();
  for (const key of ORDER) {
    if (s.startsWith(key)) return key;
  }
  return s.includes("article") ? "article" : null;
}

export interface SourceDotsProps {
  sources: string[];
  className?: string;
}

export function SourceDots({ sources, className }: SourceDotsProps): JSX.Element {
  const present = new Set(sources.map(normalize).filter(Boolean) as string[]);
  return (
    <span
      className={cn("inline-flex items-center gap-1", className)}
      title={`Sources present: ${[...present].join(" · ") || "none"}`}
    >
      {ORDER.map((key) => (
        <span
          key={key}
          className={cn(
            "inline-block h-[6px] w-[6px] rounded-full",
            present.has(key) ? "bg-accent" : "bg-border",
          )}
          aria-label={key}
        />
      ))}
    </span>
  );
}
