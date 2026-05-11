import { cn } from "@/lib/utils";

/**
 * Select — labelled dropdown for picking one value from a small option set.
 *
 * Wraps the native `<select>` element with internal-tooling styling: 32px
 * height per DESIGN_SYSTEM §5.6, white surface, 1px border, accent focus
 * ring, custom chevron via inline SVG background (browser arrow suppressed
 * via `appearance: none`). Native semantics give keyboard nav + screen reader
 * support out of the box.
 *
 * Deviation note: §5.6 mandates a custom (non-native) dropdown with hover
 * highlight and accent-soft selection fill. Native select traded in here for
 * pilot scale (2 products / 2 brands); custom dropdown can land later
 * without changing the Select callsite contract.
 */

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}

// Inline chevron — keeps the bundle clean of an icon dep. `currentColor`
// matches the select's text color so disabled state dims the arrow too.
const CHEVRON_SVG =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 1 5 5 9 1"/></svg>`,
  );

export function Select({
  label,
  value,
  options,
  onChange,
  placeholder,
  disabled,
  id,
  className,
}: SelectProps): JSX.Element {
  const selectId = id ?? `select-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label
        htmlFor={selectId}
        className="text-xs font-semibold uppercase tracking-wide text-fg-muted"
      >
        {label}
      </label>
      <select
        id={selectId}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        style={{
          backgroundImage: `url("${CHEVRON_SVG}")`,
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 10px center",
          appearance: "none",
        }}
        className={cn(
          "h-8 w-full rounded-sm border border-border bg-surface pl-3 pr-8 text-sm text-fg",
          "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft",
          "disabled:cursor-not-allowed disabled:bg-surface-alt disabled:text-fg-muted",
        )}
      >
        {placeholder !== undefined && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
