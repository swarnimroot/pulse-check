import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Pulsing placeholder block. Drop-in replacement for "Loading…" text.
 * Caller sizes + tints per spot via `className`. Default tint is
 * `bg-muted` (surface-alt §2.1); pass `bg-accent-soft` for on-brand
 * prominent skeletons (brief panel, product card).
 */
export function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={cn("animate-pulse rounded bg-muted", className)}
      {...props}
    />
  );
}
