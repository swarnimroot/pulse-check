import { cn } from "@/lib/utils";

/**
 * SourceMark — small letter-mark for source identity.
 *
 * Functional disambiguator on dense card lists, not decoration.
 * Per DESIGN_SYSTEM §3.4 — fixed brand-ish colours.
 */

type SourceKey = "reddit" | "bestbuy" | "amazon" | "youtube" | "article";

const SOURCE_MAP: Record<SourceKey, { bg: string; letter: string; label: string }> = {
  reddit: { bg: "#FF4500", letter: "R", label: "Reddit" },
  bestbuy: { bg: "#0046BE", letter: "B", label: "Best Buy" },
  amazon: { bg: "#232F3E", letter: "A", label: "Amazon" },
  youtube: { bg: "#FF0000", letter: "Y", label: "YouTube" },
  article: { bg: "#444444", letter: "·", label: "Article" },
};

function normalize(sourceType: string): SourceKey {
  const s = sourceType.toLowerCase();
  if (s.startsWith("reddit")) return "reddit";
  if (s.startsWith("bestbuy")) return "bestbuy";
  if (s.startsWith("amazon")) return "amazon";
  if (s.startsWith("youtube")) return "youtube";
  return "article";
}

export interface SourceMarkProps {
  source: string;
  size?: "sm" | "md";
  className?: string;
}

export function SourceMark({ source, size = "sm", className }: SourceMarkProps): JSX.Element {
  const key = normalize(source);
  const { bg, letter, label } = SOURCE_MAP[key];
  const dim = size === "md" ? "h-[14px] w-[14px] text-[10px]" : "h-[12px] w-[12px] text-[9px]";
  return (
    <span
      title={label}
      style={{ backgroundColor: bg }}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-sm font-semibold leading-none text-fg-on-dark",
        dim,
        className,
      )}
      aria-label={label}
    >
      {letter}
    </span>
  );
}

export function sourceLabel(sourceType: string): string {
  return SOURCE_MAP[normalize(sourceType)].label;
}
