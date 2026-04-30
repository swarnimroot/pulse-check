import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Tailwind config wired to DESIGN_SYSTEM §3 tokens.
 *
 * All colour values resolve to CSS custom properties defined in
 * `src/index.css`. This keeps raw hex values in one place so the token table
 * in the design doc stays the single source of truth. Future shadcn/ui
 * components pick up the theme via the mapped semantic names
 * (`background`, `foreground`, `primary`, ...).
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Raw surface stack from DESIGN_SYSTEM §3.1.
        surface: {
          0: "var(--surface-0)",
          1: "var(--surface-1)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
        },
        // Text stack from §3.2.
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-tertiary": "var(--text-tertiary)",
        "text-on-accent": "var(--text-on-accent)",
        // Accent stack from §3.3.
        accent: {
          DEFAULT: "var(--accent-primary)",
          hover: "var(--accent-hover)",
          subtle: "var(--accent-subtle)",
          muted: "var(--accent-muted)",
        },
        // Sentiment / intensity / addressability tokens §3.4.
        sentiment: {
          positive: "var(--sentiment-positive)",
          neutral: "var(--sentiment-neutral)",
          negative: "var(--sentiment-negative)",
        },
        intensity: {
          low: "var(--intensity-low)",
          medium: "var(--intensity-medium)",
          high: "var(--intensity-high)",
        },
        addr: {
          messaging: "var(--addr-messaging)",
          software: "var(--addr-software)",
          hardware: "var(--addr-hardware)",
          pricing: "var(--addr-pricing)",
          mixed: "var(--addr-mixed)",
        },
        // Borders — kept separate so `border-subtle` etc. is usable directly.
        "border-subtle": "var(--border-subtle)",
        "border-strong": "var(--border-strong)",
        // shadcn/ui semantic aliases — map to our tokens so shadcn components
        // inherit the theme without further wiring.
        background: "var(--surface-0)",
        foreground: "var(--text-primary)",
        card: {
          DEFAULT: "var(--surface-1)",
          foreground: "var(--text-primary)",
        },
        popover: {
          DEFAULT: "var(--surface-3)",
          foreground: "var(--text-primary)",
        },
        primary: {
          DEFAULT: "var(--accent-primary)",
          foreground: "var(--text-on-accent)",
        },
        secondary: {
          DEFAULT: "var(--surface-2)",
          foreground: "var(--text-primary)",
        },
        muted: {
          DEFAULT: "var(--surface-2)",
          foreground: "var(--text-secondary)",
        },
        destructive: {
          DEFAULT: "var(--sentiment-negative)",
          foreground: "var(--text-primary)",
        },
        border: "var(--border-subtle)",
        input: "var(--border-subtle)",
        ring: "var(--accent-primary)",
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "8px",
        md: "8px",
        lg: "12px",
      },
      fontFamily: {
        display: ["alienware", "Eurostile", "Exo 2", "Rajdhani", "sans-serif"],
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "Cascadia Code", "JetBrains Mono", "monospace"],
      },
      fontSize: {
        // §3.5 display scale. Tailwind lets us declare [size, { lineHeight, letterSpacing, fontWeight }].
        display: ["2rem", { lineHeight: "2.5rem", letterSpacing: "-0.01em", fontWeight: "600" }],
        h1: ["1.5rem", { lineHeight: "2rem", fontWeight: "600" }],
        h2: ["1.25rem", { lineHeight: "1.75rem", fontWeight: "600" }],
        h3: ["1rem", { lineHeight: "1.5rem", fontWeight: "600" }],
        body: ["0.875rem", { lineHeight: "1.25rem" }],
        label: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.02em", fontWeight: "500" }],
        "agg-lg": ["3rem", { lineHeight: "3.25rem", fontWeight: "600" }],
        "agg-inline": ["1rem", { lineHeight: "1.25rem", fontWeight: "600" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0, 0, 0, 0.3)",
      },
    },
  },
  plugins: [animate],
};

export default config;
