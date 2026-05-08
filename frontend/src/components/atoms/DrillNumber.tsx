import { cn } from "@/lib/utils";

/**
 * DrillNumber — discreet hover affordance over an aggregate count.
 *
 * Per DESIGN_SYSTEM §3.2: cursor zoom-in on hover, accent underline appears,
 * click opens an EvidenceDrawer with the relevant mention pool.
 */

export interface DrillNumberProps {
  value: number | string;
  onClick?: () => void;
  title?: string;
  className?: string;
  align?: "left" | "right";
}

const NUMBER_FMT = new Intl.NumberFormat("en-US");

function format(value: number | string): string {
  if (typeof value === "number") return NUMBER_FMT.format(value);
  return value;
}

export function DrillNumber({
  value,
  onClick,
  title,
  className,
  align = "left",
}: DrillNumberProps): JSX.Element {
  const interactive = !!onClick;
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={!interactive}
      className={cn(
        "tabular inline-block bg-transparent p-0 text-sm text-fg",
        align === "right" && "text-right",
        interactive
          ? "cursor-zoom-in hover:text-accent hover:underline hover:underline-offset-2 hover:decoration-accent"
          : "cursor-default",
        className,
      )}
    >
      {format(value)}
    </button>
  );
}
