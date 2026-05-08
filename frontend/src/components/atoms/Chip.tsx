import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Chip — small inline token. Single shape, semantic tones only.
 *
 * Geometry per DESIGN_SYSTEM §3.1 / §4.1: 18px height, 6px horizontal
 * padding, 2px radius, 11px text, 500 weight.
 */

export type ChipTone =
  | "pos"
  | "neg"
  | "neu"
  | "high"
  | "med"
  | "low"
  | "messaging"
  | "software"
  | "hardware"
  | "pricing"
  | "mixed"
  | "meta"
  | "verified"
  | "tombstone";

const TONE_CLASSES: Record<ChipTone, string> = {
  pos: "bg-success-soft text-success",
  neg: "bg-danger-soft text-danger",
  neu: "bg-surface-alt text-fg-muted",
  high: "bg-danger-soft text-danger",
  med: "bg-warning-soft text-warning",
  low: "bg-surface-alt text-fg-muted",
  messaging: "bg-accent-soft text-accent-hover",
  software: "bg-success-soft text-success",
  hardware: "bg-warning-soft text-warning",
  pricing: "bg-accent-soft text-accent-hover",
  mixed: "bg-surface-alt text-fg-muted",
  meta: "bg-surface-alt text-fg-muted",
  verified: "bg-success-soft text-success",
  tombstone: "bg-surface-alt text-fg-muted italic",
};

export interface ChipProps {
  tone: ChipTone;
  children: ReactNode;
  className?: string;
}

export function Chip({ tone, children, className }: ChipProps): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex h-[18px] items-center rounded-sm px-1.5 text-[11px] font-medium leading-none",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
