import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Tailwind config wired to DESIGN_SYSTEM §2 tokens.
 *
 * Raw colour values live in `src/index.css` as `--aw-*` custom properties;
 * Tailwind class names resolve to var() refs so component code never touches
 * raw hex. Both shadcn semantic aliases (`background`, `foreground`,
 * `primary`, ...) and direct token names (`surface`, `accent`, `success`)
 * are exposed.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Direct §2 tokens.
        surface: {
          DEFAULT: "var(--aw-surface)",
          alt: "var(--aw-surface-alt)",
          dark: "var(--aw-surface-dark)",
          "dark-alt": "var(--aw-surface-dark-alt)",
        },
        fg: {
          DEFAULT: "var(--aw-fg)",
          secondary: "var(--aw-fg-secondary)",
          muted: "var(--aw-fg-muted)",
          "on-dark": "var(--aw-fg-on-dark)",
          "on-accent": "var(--aw-fg-on-accent)",
        },
        accent: {
          DEFAULT: "var(--aw-accent)",
          hover: "var(--aw-accent-hover)",
          soft: "var(--aw-accent-soft)",
        },
        success: {
          DEFAULT: "var(--aw-success)",
          soft: "var(--aw-success-soft)",
        },
        warning: {
          DEFAULT: "var(--aw-warning)",
          soft: "var(--aw-warning-soft)",
        },
        danger: {
          DEFAULT: "var(--aw-danger)",
          soft: "var(--aw-danger-soft)",
        },
        chart: {
          1: "var(--aw-chart-1)",
          2: "var(--aw-chart-2)",
          3: "var(--aw-chart-3)",
          4: "var(--aw-chart-4)",
          5: "var(--aw-chart-5)",
          6: "var(--aw-chart-6)",
        },
        // shadcn/ui semantic aliases.
        background: "var(--aw-surface)",
        foreground: "var(--aw-fg)",
        card: {
          DEFAULT: "var(--aw-surface)",
          foreground: "var(--aw-fg)",
        },
        popover: {
          DEFAULT: "var(--aw-surface)",
          foreground: "var(--aw-fg)",
        },
        primary: {
          DEFAULT: "var(--aw-accent)",
          foreground: "var(--aw-fg-on-accent)",
        },
        secondary: {
          DEFAULT: "var(--aw-surface-alt)",
          foreground: "var(--aw-fg)",
        },
        muted: {
          DEFAULT: "var(--aw-surface-alt)",
          foreground: "var(--aw-fg-muted)",
        },
        destructive: {
          DEFAULT: "var(--aw-danger)",
          foreground: "var(--aw-fg-on-accent)",
        },
        border: "var(--aw-border)",
        "border-strong": "var(--aw-border-strong)",
        input: "var(--aw-border)",
        ring: "var(--aw-accent)",
      },
      borderRadius: {
        // §2.8 — sm 2 / md 4 / lg 8 (max).
        sm: "2px",
        DEFAULT: "4px",
        md: "4px",
        lg: "8px",
      },
      fontFamily: {
        // §3.1 — system stack (display fonts retired session 13).
        sans: ['"Arial Nova"', '"Arial"', '"Helvetica Neue"', "Helvetica", "sans-serif"],
        mono: ['"SF Mono"', '"Consolas"', '"Roboto Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        // §3.2 — fixed scale.
        xs: ["12px", { lineHeight: "1.45" }],
        sm: ["14px", { lineHeight: "1.45" }],
        base: ["16px", { lineHeight: "1.45" }],
        md: ["18px", { lineHeight: "1.45", fontWeight: "600" }],
        lg: ["24px", { lineHeight: "1.2", fontWeight: "600" }],
        xl: ["32px", { lineHeight: "1.2", fontWeight: "600" }],
      },
      boxShadow: {
        card: "var(--aw-shadow-card)",
      },
      transitionTimingFunction: {
        aw: "var(--aw-ease)",
      },
      transitionDuration: {
        1: "var(--aw-duration-1)",
        2: "var(--aw-duration-2)",
        3: "var(--aw-duration-3)",
      },
    },
  },
  plugins: [animate],
};

export default config;
