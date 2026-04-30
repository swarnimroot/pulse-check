# pulse-check — Design System

**Status:** draft &nbsp;·&nbsp; **Paired docs:** [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md)

Tokens, component conventions, and screen inventory for the pulse-check webapp. Implementation stack: Tailwind CSS + shadcn/ui components on Vite + React + TypeScript. Desktop-only, dark-mode-first, exec-clarity over analyst-depth.

---

## 1. Intent

What this doc *is*: a concrete starting set of design tokens, component patterns, and screen structures the build can start from. Everything here is **opinionated enough to build against** and **lean enough to revise** once the first screens land and we see real data.

What this doc *is not*: a pixel-perfect mockup spec. The Alienware brand inputs we have (Pompeii output) are aesthetic direction, not a spec. Specific colors, scales, and layouts below are derived from the stated direction + shadcn's baseline + industry norms for exec dashboards, and will refine during build.

One rule above all: **the design serves the content, not the brand.** An exec needs to see the finding in five seconds — not wade through chrome. Brand character applies to the frame; content areas stay disciplined and legible.

---

## 2. Brand anchoring

From the operator-provided Pompeii brand output:

- **Values:** Relentless Innovation, Uncompromising Quality, Community Collaboration, Performance Excellence
- **Visual aesthetics:** Technological Innovation, Futuristic Immersion, Sleek Minimalism, Professional Reliability, High-Tech Humanism
- **Tone of voice:** Authoritative, Futuristic, High-tech, Confident
- **Font:** `alienware` (custom, proprietary)

**Derived direction:**
- Dark-mode-first interface — the default Alienware surface treatment; also best for data-dense screens over long reads.
- Minimal chrome, high-contrast type, disciplined use of accent color.
- Geometric / tech-sans typography for display; neutral humanist sans for body (readability wins over stylistic consistency).
- No gamer-y excess — no RGB glow, no neon chrome, no ambient motion. Professional exec read.

**Honest note on the font.** The `alienware` font is proprietary; it is unlikely we can redistribute it. The design uses a fallback chain: `alienware` (if licensed/installed) → `Eurostile` → `Exo 2` → `Rajdhani` → system sans. Display headings get the tech-sans stack; body copy uses `Inter` (clean, reliable, free).

---

## 3. Design tokens

All tokens exposed as CSS custom properties in the Tailwind config. shadcn/ui theme variables map to these.

### 3.1 Color — surfaces (dark-mode primary)

| Token | Value | Use |
|---|---|---|
| `--surface-0` | `#0B0B0D` | App background (near-black, not pure) |
| `--surface-1` | `#141416` | Card / panel |
| `--surface-2` | `#1E1E22` | Elevated card (card-on-card, hover state) |
| `--surface-3` | `#282830` | Popover / drawer |
| `--border-subtle` | `#2A2A30` | Default card border |
| `--border-strong` | `#3A3A42` | Focus / emphasis |

### 3.2 Color — text

| Token | Value | Use |
|---|---|---|
| `--text-primary` | `#F5F5F7` | Headings, primary copy, aggregate numbers |
| `--text-secondary` | `#9A9AA4` | Body labels, metadata |
| `--text-tertiary` | `#6A6A74` | Captions, disabled, hints |
| `--text-on-accent` | `#0B0B0D` | Text on accent-filled backgrounds |

### 3.3 Color — accent (Alienware signature)

| Token | Value | Use |
|---|---|---|
| `--accent-primary` | `#00D4FF` | Alienware "plasma blue"; primary CTAs, links, focus rings |
| `--accent-hover` | `#33DDFF` | Hover state |
| `--accent-subtle` | `rgba(0, 212, 255, 0.12)` | Tint backgrounds, subtle fills |
| `--accent-muted` | `#0097B8` | Secondary accent uses |

### 3.4 Color — semantic (sentiment + intensity + addressability)

Sentiment polarity (muted, not screaming — this is exec-read):

| Token | Value | Use |
|---|---|---|
| `--sentiment-positive` | `#3AB58A` | Positive sentiment pill, bar, score |
| `--sentiment-neutral` | `#6A6A74` | Neutral sentiment |
| `--sentiment-negative` | `#D35268` | Negative sentiment (muted red, not pure red) |

Intensity (for tag chips + distribution bars):

| Token | Value | Use |
|---|---|---|
| `--intensity-low` | `#5A6B7A` | Low-intensity mentions |
| `--intensity-medium` | `#C48A3A` | Medium-intensity mentions |
| `--intensity-high` | `#D35268` | High-intensity mentions (shared with neg-sentiment; contextually OK) |

Addressability badges (A2):

| Token | Value | Use |
|---|---|---|
| `--addr-messaging` | `#00D4FF` | Messaging/PR-addressable reasons (accent blue) |
| `--addr-software` | `#3AB58A` | Software-addressable (green) |
| `--addr-hardware` | `#C48A3A` | Hardware-addressable (amber — implies cost/complexity) |
| `--addr-pricing` | `#9B6AD8` | Pricing-addressable (purple) |
| `--addr-mixed` | `#6A6A74` | Mixed / ambiguous |

### 3.5 Typography

```
Display:    alienware | Eurostile | Exo 2 | Rajdhani | sans-serif
Body / UI:  Inter | system-ui | -apple-system | sans-serif
Mono / num: ui-monospace | "Cascadia Code" | "JetBrains Mono" | monospace
```

Body + UI use `Inter` via Google Fonts — reliable, free, excellent at small sizes.

Scale (Tailwind default, documented per usage):

| Role | Size | Weight | Tracking |
|---|---|---|---|
| Display (page headline) | 32px / 2rem | 600 | −1% |
| H1 (section) | 24px / 1.5rem | 600 | normal |
| H2 (subsection) | 20px / 1.25rem | 600 | normal |
| H3 (card title) | 16px / 1rem | 600 | normal |
| Body | 14px / 0.875rem | 400 | normal |
| Body strong | 14px | 600 | normal |
| Label / caption | 12px / 0.75rem | 500 | +2% (uppercase for chip labels) |
| Aggregate number (large) | 40px–56px | 600 | tabular-nums |
| Aggregate number (inline) | 16px | 600 | tabular-nums |

**Numbers use `font-variant-numeric: tabular-nums`** so columns of aggregate counts align cleanly. This is not optional.

### 3.6 Spacing, radius, shadow

Tailwind defaults unless otherwise noted.

- **Spacing base:** 4px. Common rhythms: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- **Radius:** `4px` (chips / inputs), `8px` (cards / buttons), `12px` (drawers / dialogs). No heavy rounding.
- **Shadow:** subtle, purposeful only. Default: `0 1px 2px rgba(0,0,0,.3)` for cards on `--surface-0`; stronger only for drawers/popovers.

---

## 4. Component conventions

Components build on shadcn/ui; conventions below define how the app *uses* them.

### 4.1 VerbatimCard — the evidence atom

Every drill-down renders a stack of these. Every claim the UI makes eventually leads here.

```
┌───────────────────────────────────────────────────┐
│  [icon] Reddit · r/GamingLaptops  ·  ↗           │
│  Posted Mar 14, 2026 · u/example_user              │
│                                                    │
│  "Picked the Strix G16 over the Area-51 18        │
│   because Alienware runs way hotter under load.    │
│   Tested both at Micro Center."                    │
│                                                    │
│  ┌─────────────────┬─────────────────────────┐    │
│  │ thermals · neg  │ high intensity          │    │
│  └─────────────────┴─────────────────────────┘    │
│                                                    │
│  [verified purchase] [owned 6 months] [↑ 142]     │
└───────────────────────────────────────────────────┘
```

Required elements:
- **Source icon + source label + channel** (top-left). Source URL clickable (↗ icon).
- **Publish date + author** (second line, `--text-secondary`).
- **Verbatim text**, rendered from DB (never from LLM output). Quotation indent.
- **Aspect tag chips** — `aspect · polarity` pill + `intensity` pill.
- **Metadata chips** — verified_purchase, ownership_duration, upvotes / helpful_count, rating, etc. Only show chips that have actual values.
- **Tombstone badge** (if `tombstoned_at` set) — small red-orange pill: "no longer available on source".

Variants:
- **Compact** — list item in a stack, body text truncated to 3 lines with "show more"
- **Expanded** — full text, shown in drawer or on hover expansion

### 4.2 AggregateNumber — the drillable number

Any number that was computed from mentions is rendered as `AggregateNumber`. Implicit contract: **clicking opens the evidence drawer with the contributing mentions**.

Visual:
- Tabular nums, `--text-primary`
- Subtle underline-dot or magnifier icon on hover to signal clickability
- Cursor pointer
- Accessible: role="button", aria-label includes context ("61% win rate — 147 threads — show evidence")

Non-drillable metadata numbers (count-of-sources, last-updated-timestamp) render as plain text; no affordance.

### 4.3 AspectRow — A1 scorecard row

Rendered as a single row per aspect on the product scorecard. Horizontal, scannable.

```
┌──────────────┬──────────┬────────┬──────────────────────┬─────────┬───────────┬────┐
│ Aspect       │  Net     │ Count  │ Intensity dist       │ Verif % │ Sources   │ ↗  │
├──────────────┼──────────┼────────┼──────────────────────┼─────────┼───────────┼────┤
│ Thermals     │   −0.42  │   342  │ ▓▓▓▓▓░░░░░ (32 H)   │   71%   │ ● ● ● ● ● │ ↗  │
│ Performance  │   +0.18  │   289  │ ▓▓░░░░░░░░ (6 H)    │   74%   │ ● ● ● ●   │ ↗  │
│ Keyboard     │   +0.51  │   201  │ ▓░░░░░░░░░ (2 H)    │   80%   │ ● ● ●     │ ↗  │
│ ...                                                                              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- `Net` — signed float, color-coded by sentiment token
- `Count` — total mentions; AggregateNumber (drillable)
- `Intensity dist` — small stacked bar (low / med / high on negative side) + inline "(X H)" count of high-intensity mentions
- `Verif %` — share of contributing mentions with `verified_purchase=True`
- `Sources` — filled dots per source type (Reddit / BestBuy / Amazon / YouTube / Article); unfilled if absent
- `↗` — expand row into verbatim drill-down drawer

### 4.4 ReasonRow — A2 per-reason row

Same pattern as AspectRow but per reason bucket within a pair winner-side.

```
┌──────────────────────┬────────┬──────────────┬───────────────┬──────────┬────┐
│ Reason               │ Count  │ Intensity    │ Addressability│ Preview  │ ↗  │
├──────────────────────┼────────┼──────────────┼───────────────┼──────────┼────┤
│ Thermal design       │   60   │ 28 H / 22 M  │ [hardware]    │ "runs... │ ↗  │
│ Aesthetic restraint  │   44   │ 12 H / 18 M  │ [messaging]   │ "looks...│ ↗  │
│ Software bloat       │   38   │ 19 H / 12 M  │ [software]    │ "Comm... │ ↗  │
└─────────────────────────────────────────────────────────────────────────────┘
```

Addressability chip uses the `--addr-*` token colors. Preview shows first ~40 chars of the Sonnet-selected representative verbatim.

### 4.5 WinRateHeader — A2 headline

Large, confident, centered on the pair view.

```
           Alienware 16 Aurora  vs.  ROG Strix G16

                      39%    ·    61%
                       147 of 240 resolved deliberation threads
                                      chose the Strix G16

                              [show all 240 threads ↗]
```

- Big numbers: `Aggregate number (large)` size, sentiment-neutral color
- Subtitle: plain body copy with the count (AggregateNumber drillable)
- Link: opens evidence drawer filtered to the 240 threads

### 4.6 BriefPanel — Sonnet narrative with inline citations

Renders `briefs.narrative` JSON as prose with inline citation markers.

```
  Top losing reasons

  Thermals is the top-cited reason deliberators chose the Strix G16 over
  the Area-51 18, appearing in 60 resolved threads. [1][2][3] These
  complaints cluster around sustained-load temperatures and fan noise —
  60% of cited threads call out the Alienware's cooling design specifically.

                                       ─────

  Addressability breakdown

  All three top losing reasons are perception- or software-addressable...
```

- `[1][2][3]` — small superscript citation markers, styled as `--accent-primary` subscript
- **Hover** a marker → small tooltip with the first cited verbatim (source + 1-line excerpt)
- **Click** a marker → pins the evidence panel on the right, with all cited mentions for that claim, other markers in the brief deselect

### 4.7 EvidenceDrawer — universal drill-down

Always slides in from right when any AggregateNumber / citation / expand-row affordance is triggered. One at a time; clicking another affordance updates its content.

```
┌────────────────────────────────────────┐
│ 342 mentions · thermals · Area-51 18   │  ← header: count + context
│ [×]                                     │
│ ─────                                   │
│ [Filters: source ▾] [verified ◻]       │  ← filters (pre-computed)
│  [recency ▾] [intensity ▾]             │
│ ─────                                   │
│ [VerbatimCard]                          │  ← stack of compact cards
│ [VerbatimCard]                          │
│ [VerbatimCard]                          │
│ ...                                     │
│ [Load more]                             │
└────────────────────────────────────────┘
```

Width: ~440px on desktop. Body scrolls; header + filters pin.

### 4.8 Chip / badge patterns

One shape, tonal variants:

- **Sentiment chip** — `aspect · polarity` shown together: `thermals · neg` with polarity color fill
- **Intensity chip** — `low` / `med` / `high` with intensity token color
- **Addressability chip** — `[messaging]` / `[software]` / `[hardware]` / `[pricing]` with `--addr-*` color
- **Metadata chip** — `verified purchase`, `owned 6 months`, `↑ 142`, `★ 4.2` — monochrome, muted border
- **Tombstone chip** — orange/red muted, "no longer available"

All chips: `4px` radius, `10px–11px` text, `4px` vertical / `8px` horizontal padding.

### 4.9 Charts

shadcn/ui's Chart component (Recharts-based) is the default. Only three chart types needed for v1:

- **Stacked bar** — intensity distribution per aspect/reason. Horizontal.
- **Horizontal bar** — source-breakdown of an aspect's mentions.
- **Sparkline** — optional recency trend per aspect (30d window).

No pie charts. No 3D. No animations beyond a 150ms mount fade.

Chart palette reuses `--sentiment-*` + `--intensity-*` tokens — never introduce new chart colors.

---

## 5. Screen inventory

Three routes + one overlay. Minimal.

### 5.1 `/` — Landing / selector

Shown at app open. Two tabs: "Standalone voice" (A1) and "Comparative deliberation" (A2). Under each, a selector:
- **A1:** dropdown of all products in the current run → navigates to `/product/:product_id`
- **A2:** dropdown of all configured pairs → navigates to `/pair/:pair_id`

Top-of-page: small run-metadata strip — "Run: demo_2026_04 · 6mo backfill · taxonomy v0 · generated 2026-04-23".

### 5.2 `/product/:product_id` — A1 scorecard

Page structure:
```
┌──────────────────────────────────────────────────┐
│ [← back]  Alienware 16 Aurora                     │
│ 2,847 mentions · 6mo window                       │
├──────────────────────────────────────────────────┤
│ [Cohort toggles: ◻ verified only  ◻ last 30d]    │
├──────────────────────────────────────────────────┤
│  AspectRow × 11 (table)                          │
├──────────────────────────────────────────────────┤
│  BriefPanel — A1 standalone brief                 │
└──────────────────────────────────────────────────┘
```

### 5.3 `/pair/:pair_id` — A2 pair view

```
┌──────────────────────────────────────────────────┐
│ [← back]    [pair selector ▾]                    │
├──────────────────────────────────────────────────┤
│                   WinRateHeader                   │
├──────────────────────────────────────────────────┤
│  Left column                Right column          │
│  Why [primary] won          Why [competitor] won  │
│  ReasonRow × 6              ReasonRow × 6         │
├──────────────────────────────────────────────────┤
│  BriefPanel — A2 comparative brief                │
└──────────────────────────────────────────────────┘
```

### 5.4 Evidence drawer

Overlay, not a route. Any AggregateNumber / expand-row / citation opens it. Described in §4.7.

---

## 6. Interaction & motion

Minimal and purposeful. The aesthetic is confident-quiet, not animated-loud.

- **Hover states:** color shift (100ms), optional subtle translate-y for cards (`transform: translateY(-1px)`)
- **Drawer open:** 240ms ease-out slide-in from right
- **Tab switch:** instant; content area gets a 120ms fade
- **Citation pin:** 120ms fade-in for the right-side evidence panel
- **Chart mount:** 150ms bar-grow or fade-in

NOT in scope: parallax, auto-scrolling, ambient shimmer, RGB effects, glitch / scanline chrome.

---

## 7. Accessibility

- WCAG AA contrast ratios for all text/background pairs
- Focus rings visible (`--accent-primary` outline, 2px, 2px offset) — never removed
- All drillable numbers + citation markers are `role="button"` with descriptive `aria-label`s
- Keyboard: tab order follows reading order; Esc closes drawers; Enter/Space activate drillables
- Screen reader: AggregateNumber announces "147, clickable — show 147 contributing mentions"
- Respect `prefers-reduced-motion` — disable transforms, keep fades only
- No color-only information: sentiment always carries a label (`neg` / `pos`) alongside color; intensity always carries a count alongside fill

---

## 8. Implementation notes

### 8.1 Tailwind config

Tokens exposed as CSS variables; Tailwind `theme.extend.colors` maps to `var(--...)`. Example shape:

```js
// tailwind.config.js (sketch, not final)
module.exports = {
  darkMode: ['class'],
  theme: {
    extend: {
      colors: {
        surface: {
          0: 'var(--surface-0)',
          1: 'var(--surface-1)',
          2: 'var(--surface-2)',
          3: 'var(--surface-3)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
        },
        accent: {
          DEFAULT: 'var(--accent-primary)',
          hover: 'var(--accent-hover)',
          subtle: 'var(--accent-subtle)',
          muted: 'var(--accent-muted)',
        },
        sentiment: {
          positive: 'var(--sentiment-positive)',
          neutral: 'var(--sentiment-neutral)',
          negative: 'var(--sentiment-negative)',
        },
        intensity: {
          low: 'var(--intensity-low)',
          medium: 'var(--intensity-medium)',
          high: 'var(--intensity-high)',
        },
        addr: {
          messaging: 'var(--addr-messaging)',
          software: 'var(--addr-software)',
          hardware: 'var(--addr-hardware)',
          pricing: 'var(--addr-pricing)',
          mixed: 'var(--addr-mixed)',
        },
      },
      fontFamily: {
        display: ['alienware', 'Eurostile', 'Exo 2', 'Rajdhani', 'sans-serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['ui-monospace', 'Cascadia Code', 'JetBrains Mono', 'monospace'],
      },
    },
  },
};
```

### 8.2 shadcn/ui integration

- Install shadcn/ui CLI; generate component stubs as needed (Card, Table, Sheet for drawer, Dialog, Tabs, Select, Popover, Tooltip, Badge, Chart, Separator).
- Theme variables (`--background`, `--foreground`, `--muted`, `--primary`, etc.) map to our surface/text/accent tokens in a single `app.css`.
- Dark-mode is the only mode — no theme toggle in v1.

### 8.3 Font strategy

- `Inter` loaded from Google Fonts via `<link>` in the HTML head (subset: `latin`).
- Display fallback chain declared in CSS; if the `alienware` font file is available + licensed, declare it via `@font-face`. Otherwise the chain quietly degrades to Exo 2 (Google Fonts) → Rajdhani (Google Fonts) → system sans. All usable.

### 8.4 Dark-mode-only for v1

Light mode is explicitly out of scope for v1 (PRD §4.2). The Tailwind `darkMode: 'class'` setting is kept for forward compatibility, but the app root always has the `dark` class applied. No toggle, no user preference read. Revisit if exec feedback requests it later.

---

## 9. What's explicitly not specified here

These will land during build, with decisions flagged in-conversation per CLAUDE.md §doc-evolution:

- Exact chart widths, paddings, and responsive breakpoints under 1280px
- Empty-state illustrations / copy (when a product has <100 mentions for a pair)
- Loading skeletons (shadcn defaults will do initially)
- Error states (network, 404, partial-data)
- Exact copy tone for UI microcopy — to be drafted during build in the Authoritative-Confident voice
- Pair selector UX when the pair plan grows past ~15 (pagination / search — not a v1 concern at 10)
