# pulse-check — Design System

**Status:** v0.1 (locked at session-13 start) &nbsp;·&nbsp; **Paired docs:** [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`SESSION_LOG.md`](SESSION_LOG.md)

Tokens, atoms, composite components, and screen inventory for the pulse-check webapp. Implementation stack: Tailwind CSS + shadcn/ui as tooling on Vite + React + TypeScript. **Tokens here are the source of truth**; Tailwind config consumes them as CSS custom properties.

> **Posture pivot, session 13.** The prior draft anchored a dark-mode gaming aesthetic. Operator locked a **light, internal-tooling aesthetic** at session-13 start — derived from a claude.ai/design prototype (`bundle: pulse-check`). This doc replaces the prior draft.

---

## 1. Posture

- **Light theme.** White surface (`#FFFFFF`), `#F4F5F7` for muted zones, `#17171C` for the rare dark surface (sidebars, cover slides).
- **Internal tooling**, not a marketing surface. Information-dense; exec-clarity over analyst-depth.
- **Brand identity = logo + a single purple accent (`#5F00F8`).** Used only for: discreet hover affordances, selected/active states, citation chips, and primary buttons.
- **No gradients in content. No glow. No gaming flourish. No ambient motion.**
- **Desktop-only**, min-width 1280px. No responsive collapse for v1.
- **One rule above all:** the design serves the content. Numbers and verbatims dominate; chrome stays out of the way.

---

## 2. Tokens

All tokens declared as CSS custom properties on `:root`. Source: `tokens.css` (from the prototype bundle), reproduced here verbatim. Tailwind theme should consume these via `var(--aw-…)`.

### 2.1 Surfaces

| Token | Value | Use |
|---|---|---|
| `--aw-surface` | `#FFFFFF` | Default canvas |
| `--aw-surface-alt` | `#F4F5F7` | Subdued zones, table headers, drawer card stack |
| `--aw-surface-dark` | `#17171C` | Sidebars, nav rails, cover slides only |
| `--aw-surface-dark-alt` | `#21212A` | Hover row on dark surfaces |

### 2.2 Text

| Token | Value | Use |
|---|---|---|
| `--aw-fg` | `#17171C` | Primary copy, aggregate numbers, headings |
| `--aw-fg-secondary` | `#444444` | Body labels |
| `--aw-fg-muted` | `#6B6B73` | Captions, helper text, disabled |
| `--aw-fg-on-dark` | `#FFFFFF` | Text on dark surfaces |
| `--aw-fg-on-accent` | `#FFFFFF` | Text on purple |

### 2.3 Borders

| Token | Value | Use |
|---|---|---|
| `--aw-border` | `#D9DCE7` | Standard divider, card border |
| `--aw-border-strong` | `#AAAAAA` | Inputs, table cells, dashed empty states |

### 2.4 Accent — Alienware purple

| Token | Value | Use |
|---|---|---|
| `--aw-accent` | `#5F00F8` | Primary buttons, citation chip hover, focus |
| `--aw-accent-hover` | `#2C098C` | Hover/pressed accent |
| `--aw-accent-soft` | `#EDE7FE` | Soft fill — citation chips at rest, selected rows, selection highlight |

**Discipline:** purple appears **once or twice per screen at most**. Never as a fill on large surfaces.

### 2.5 Status

| Token | Value | Use |
|---|---|---|
| `--aw-success` | `#1F8A3F` | Positive sentiment, "what is working" chip text |
| `--aw-warning` | `#B8860B` | Medium intensity, neutral signal |
| `--aw-danger` | `#C13030` | Negative sentiment, "complaints" chip text |
| `--aw-success-soft` | `#E8F4EC` | Pos chip background |
| `--aw-warning-soft` | `#FAF1DC` | Med chip background |
| `--aw-danger-soft` | `#F8E5E5` | Neg chip background |

### 2.6 Chart

| Token | Value | Use |
|---|---|---|
| `--aw-chart-1` | `#5F00F8` | First series only (purple) |
| `--aw-chart-2` | `#00F0F0` | **Second series only** (cyan); forbidden as content color elsewhere |
| `--aw-chart-3..6` | neutrals | Tertiary series |

### 2.7 Spacing (4px grid)

| Token | px |
|---|---|
| `--aw-space-1` | 4 |
| `--aw-space-2` | 8 |
| `--aw-space-3` | 12 |
| `--aw-space-4` | 16 |
| `--aw-space-6` | 24 |
| `--aw-space-8` | 32 |
| `--aw-space-12` | 48 |
| `--aw-space-16` | 64 |
| `--aw-page-pad` | 32 |
| `--aw-card-pad` | 24 |

### 2.8 Radii

| Token | px |
|---|---|
| `--aw-radius-sm` | 2 (chips, inline markers) |
| `--aw-radius-md` | 4 (buttons, inputs, badges, drawer headers) |
| `--aw-radius-lg` | 8 (cards, scrollers — **max**) |

### 2.9 Shadows

Single elevation. Do not invent more.

```
--aw-shadow-card: 0 1px 2px rgba(23,23,28,0.06), 0 1px 3px rgba(23,23,28,0.04);
```

### 2.10 Motion

| Token | Value |
|---|---|
| `--aw-ease` | `cubic-bezier(0.2, 0, 0, 1)` |
| `--aw-duration-1` | 120ms (hover, press) |
| `--aw-duration-2` | 200ms (state transitions, drawer-in) |
| `--aw-duration-3` | 320ms (layout) |

### 2.11 Focus

```
--aw-focus-ring: 0 0 0 2px #FFFFFF, 0 0 0 4px var(--aw-accent);
```

---

## 3. Typography

### 3.1 Stack

```
--aw-font-sans: "Arial Nova", "Arial", "Helvetica Neue", Helvetica, sans-serif;
--aw-font-mono: "SF Mono", "Consolas", "Roboto Mono", ui-monospace, monospace;
```

**Pivot from prior posture:** the `Exo 2` + `Rajdhani` Google Fonts loaded by `frontend/index.html` (session 3) are no longer needed. Remove the font-link tags when 11.2 lands; system stack is the spec now.

### 3.2 Scale (web)

| Token | Size |
|---|---|
| `--aw-text-xs` | 12px (eyebrow, captions, chips, drawer meta) |
| `--aw-text-sm` | 14px (body default) |
| `--aw-text-base` | 16px (BriefPanel claim text, h4) |
| `--aw-text-md` | 18px (h3) |
| `--aw-text-lg` | 24px (h2) |
| `--aw-text-xl` | 32px (h1) |

Line heights: `--aw-line-tight: 1.2`, `--aw-line-normal: 1.45`, `--aw-line-loose: 1.6`.

Weights: `--aw-weight-regular: 400`, `--aw-weight-medium: 500`, `--aw-weight-semibold: 600` (heading weight).

### 3.3 Numerics

All counts, scores, percentages: `font-variant-numeric: tabular-nums`. Numerics in the mono stack where alignment matters (run-meta strip, drillable counts, sparkline labels).

---

## 4. Atoms

Each atom: prop / state inventory + key visual rules. Implementation lives at `frontend/src/components/<atom>.tsx`.

### 4.1 Chip

Small inline token. **Single shape**, semantic variants only — never invent new shapes for new states.

Tones (from `CHIP_TONES` in prototype `atoms.jsx`):

| Tone | Use |
|---|---|
| `pos` / `neg` / `neu` | Sentiment polarity |
| `high` / `med` / `low` | Intensity |
| `messaging` / `software` / `hardware` / `pricing` / `mixed` | A2 addressability (Wave 3) |
| `meta` | Generic neutral metadata (e.g., `↑ 142`, `★ 4.5`) |
| `verified` | Verified-purchase signal |
| `tombstone` | Deleted/no-longer-available marker (deferred per session-13 lock) |

**Geometry:** 18px height, 6px horizontal padding, 2px radius (`--aw-radius-sm`), 11px text, 500 weight.

### 4.2 DrillNumber

Discreet hover affordance for any aggregate count. Cursor `zoom-in` on hover; underline appears in `--aw-accent`. Click opens the EvidenceDrawer with the relevant `mention_ids` pool.

Props: `value`, `onClick`, `align`, `title`.

### 4.3 CiteChip (replaces prototype `CiteMarker [n]`)

**Pivot from prototype:** the prototype renders inline `[1][2]` numeric markers tied to a separate `citation_map`. Our backend (§6.3 four-quadrant brief) already attaches `cited_mention_ids` to each `Claim`, so we render a **citation chip per claim** instead — e.g., `[3 mentions]` — with the same hover-preview + click-to-pin behavior. No `[n]` numbering. No marker-to-id map.

Visual: pill at end of claim text, `--aw-accent-soft` background, `--aw-accent-hover` text, 11px size, hover flips to `--aw-accent` fill / white text. On hover: tooltip with first mention's source mark + channel + date + first 180 chars of quote. On click: opens the CitationPanel pinned to the right.

### 4.4 SourceMark

Small letter-mark for source identity. **Not decorative** — functional disambiguator on dense card lists.

| Source | BG | Letter |
|---|---|---|
| reddit | `#FF4500` | R |
| bestbuy | `#0046BE` | B |
| amazon | `#232F3E` | A |
| youtube | `#FF0000` | Y |
| article | `#444444` | · |

12–14px square, 2px radius, white letter. Used on VerbatimCard, citation tooltip, and drawer card stacks.

### 4.5 SourceDots

Five small dots in fixed source order (`reddit · bestbuy · amazon · youtube · article`). Filled where the source has any mention for this aspect. Used in the **expanded** AspectRow only — keeps the at-rest row clean.

### 4.6 IntensityBar

Horizontal stacked bar (high / med / low). Total width 100–120px. Colors: high `#C13030`, med `#B8860B`, low `#D9DCE7`. Tooltip exposes the raw counts. Expanded AspectRow only.

### 4.7 Sparkline

26-week recency volume. SVG polyline, 1.5px stroke, `--aw-accent`. 120×24 typical. Expanded AspectRow only.

> **Backend dependency:** the 26-week series isn't materialized in `aggregates_aspect_sku.by_recency` today — that field carries coarser bucket counts. 11.2 will derive the series at API-handler time from `mentions.published_at` for each aspect's `mention_ids`. Track open item if not.

### 4.8 VerbatimCard

The single most-rendered atom on the page. Section order, top-to-bottom:

1. **Source mark + source label + channel** + url-out icon (top-right).
2. **Posted date · author** (muted, 11px).
3. **Quote** in a left-bordered blockquote, 13px, 1.5 line height. Truncate at 180 chars with show-more / show-less.
4. **Tag row 1:** aspect-polarity chip + intensity chip.
5. **Tag row 2 (only if data exists):** `verified purchase` (when present) + `↑ <upvotes>` (Reddit only) + `★ <rating>` (retailer only).

**Locked exclusions per session-13:** no ownership phrase ("owned 6 months"), no tombstone marker. Re-add when there's a real workflow demand.

---

## 5. Composite components

### 5.1 AspectRow + AspectColumn (the scroller)

**Locked layout per session-13:** two scrollers per Standalone page — left = positive net sentiment, right = negative net sentiment.

**Each scroller has 3 stacked sections in scroll order:**

| Section | Contents | Sort |
|---|---|---|
| **A** | Top-3 PRIMARY rows (by `total_mentions`) for this polarity | mentions desc |
| **B** | Top-3 SECONDARY rows (by `total_mentions_secondary`), **excluding any aspect already in A of this scroller** | mentions desc |
| **C** | Long tail — every other aspect with any mentions in this polarity, **excluding A and B of this scroller** | mentions desc |

**No within-scroller repeats.** Cross-scroller divergence is permitted: an aspect with `PRIMARY pos = 0.59` and `SECONDARY neg = −0.18` (real example: rog_strix_g16 price-value) appears in **left scroller Section A** AND **right scroller Section B**. A small `primary` / `secondary` tone chip on the row tells the eye which bucket the metrics represent.

**Row at rest:** `aspect · net · mentions (drillable) · expand`. Single line, ~41px tall.

**Row expanded:** reveals `IntensityBar + high count`, `verifiedPct`, `SourceDots`, `Sparkline` in a 2×2 inset grid. Background `--aw-surface-alt`.

**Header:** polarity chip with count (e.g., `WHAT IS WORKING (6)` / `COMPLAINTS (5)`). The prior "Positives" / "Negatives" eyebrow text was removed from the prototype mid-iteration; chip-with-count carries the meaning.

**Section dividers within scroller:** TBD — see §9 open questions.

**Empty state:** dashed-border card with neutral copy. Right scroller is α-placeholder territory on both pilot products today (zero PRIMARY-backed cons); Section B (top-3 SECONDARY neg) lifts up immediately.

### 5.2 BriefPanel

**Locked four-section structure** (per §6.3 four-quadrant lock + session-13 brief shape decision). Each section maps to one quadrant of the §6.3 selector grammar:

| Section | Quadrant | Cap |
|---|---|---|
| `Q1` PRIMARY positive (e.g., `High-confidence strengths`) | Q1 | up to 3 claims |
| `Q2` PRIMARY negative (e.g., `High-confidence weaknesses`) | Q2 | up to 3 claims; α-placeholder when empty |
| `Q3` SECONDARY positive (e.g., `Low-signal strengths (public chatter)`) | Q3 | up to 3 claims |
| `Q4` SECONDARY negative (e.g., `Low-signal weaknesses (public chatter)`) | Q4 | up to 3 claims |

> **Heading literals come from the persisted `narrative.sections[i].heading`**, not from a frontend constant — Sonnet-generated headings on the live briefs read `"High-confidence strengths"`, `"High-confidence weaknesses"`, `"Low-signal strengths (public chatter)"`, `"Low-signal weaknesses (public chatter)"`. Frontend must render whatever the backend returns, in order. Section→quadrant mapping is positional (sections[0]=Q1, sections[1]=Q2, sections[2]=Q3, sections[3]=Q4), as fixed by the brief writer.

Each claim: short bullet text (Sonnet-written) ending in a `CiteChip` showing mention count. `claim_text` is the only thing the LLM authors; `cited_mention_ids` come from the deterministic selector (§6.3).

**Header:** `Brief` heading + small `AUTO-GENERATED` eyebrow.

**Background:** white card with `--aw-shadow-card`, 24px padding, 16px gap between sections.

### 5.3 EvidenceDrawer

Right-side overlay, **440px wide**, persistent until dismissed. **No scrim** — the page stays interactive; user can re-trigger drill from another row without closing.

Sections:
1. **Pinned header.** `Evidence` eyebrow · `<count> mentions · <aspect>` · `<product name>` subtitle. Close button.
2. **Pinned filters.** `source` (select), `verified` (checkbox), `recency` (select, no-op v1), `intensity` (select). Filter changes update the visible set immediately client-side.
3. **Card stack.** `--aw-surface-alt` background, 16px padding, 10px gap, vertical scroll. `Load more` button at the foot.

Animation: slide-in from right, 200ms `--aw-ease`. Esc closes.

### 5.4 CitationPanel

Right-side panel, **380px wide**, narrower than EvidenceDrawer. Opens for `CiteChip` clicks. No filters — just the cited mentions for that claim.

**Co-existence rule:** if EvidenceDrawer is also open (440px), CitationPanel offsets to `right: 440px`. Both visible simultaneously when an exec is checking citations against an aggregate.

### 5.5 RunMetaStrip

Thin band at top of every Standalone / Compare page. Locked label format per session-13:

```
1,143 mentions · 6-month window · last refreshed 2026-05-07
```

**Excluded:** run_id, taxonomy version, generated-by-pipeline metadata. The strip exists to communicate provenance + freshness, not internals.

Geometry: 28px tall, `--aw-surface-alt` background, 11px mono numerics, muted text, single bottom border.

### 5.6 Dropdown (Company / Product / pair selectors)

Custom dropdown (not native `<select>`). Click-toggle list anchored to the trigger button. Selected option highlighted with `--aw-accent-soft` fill + 600 weight. Optional `meta` text right-aligned in each option (e.g., `2,847 mentions`).

32px height for selectors; 24px for inline filter selects in the drawer.

### 5.7 Cohort toggles

**Hidden v1 per session-13.** Re-add when there's a real workflow demand.

---

## 6. Screen inventory

### 6.1 About (`#/`)

Default landing route.

- RunMetaStrip
- Title + 1-line intro: `pulse-check surfaces what owners are actually saying about your products.`
- **Standalone selector** card: `Company` dropdown (filters product list) + `Product` dropdown + `Open standalone →` button.
- **Compare placeholder** card: greyed-out, `Wave 3 — coming soon` badge. No selectors active.
- **No 5-stage explainer** for v1. Add when the pilot is mature.

### 6.2 Standalone (`#/standalone[/:productId]`)

A1 product voice page. Locked layout per session-13:

1. RunMetaStrip
2. Header strip: `Home` back button · `A1 · Standalone voice` eyebrow · selector (right-aligned).
3. Sub-header: product name h1 · `<n> mentions · <window>` (drillable count opens drawer with all mention_ids).
4. **Two-column scroller:** §5.1 — left positive | right negative, each with Sections A / B / C.
5. **BriefPanel:** §5.2 — four labeled sections with citation chips.

Empty state when no `productId` in route: dashed empty-state card prompting selector use.

### 6.3 Compare (`#/compare`) — Wave 3 placeholder

`Wave 3 — coming soon` empty state. No selectors. Operator can point at this during demo to communicate the roadmap.

---

## 7. Anti-patterns

What this design **must not** do — these will read as off-brand and need rework if introduced:

- **Gradients in content.** Solid fills only.
- **Glow / drop-shadow effects** beyond `--aw-shadow-card`. Single elevation, no neon.
- **Gaming flourish** — no RGB strips, no hexagonal frames, no cyberpunk type, no animated scan lines.
- **Dark backgrounds in content areas.** `--aw-surface-dark` is reserved for sidebars / cover slides, not the scorecard or brief panel.
- **Multiple citation styles.** One brief = one citation paradigm (chips per claim, no `[n]` markers). Don't mix.
- **Ambient motion.** Animations only on state transitions (hover, drawer in/out, mount fade). No looping motion.
- **Brand color overuse.** Purple is for affordance and accent. Never as a content fill on a card or panel.
- **Reinventing chip shapes.** New states get new tones, not new shapes.
- **`--aw-chart-cyan` as a content color.** Chart series 2 only.

---

## 8. Implementation pointers

- **Entry HTML** of the prototype: `frontend/public/pulse-check.html` reference at `/tmp/pulse-design/pulse-check/project/pulse-check.html`. Hash routing pattern: `#/`, `#/standalone[/:productId]`, `#/compare`.
- **Prototype source**: `/tmp/pulse-design/pulse-check/project/{atoms,product,drawer,selector}.jsx`. Translate to TS+React; tokens reference via `var(--aw-…)`. Keep prototype's structure where it earns its keep; rewrite where ours diverges (CiteChip vs CiteMarker, four-quadrant BriefPanel vs three-section).
- **Tailwind config** consumes the tokens via `extend.colors`, `extend.spacing`, etc. Don't duplicate values in component code.
- **Backend contracts** locked in 11.1: `pulse_check/api/schemas.py` — `ProductSummary`, `ProductDetail` (with PRIMARY+SECONDARY `AspectRow`), `MentionView`, `BriefView`. Frontend codes against these.

---

## 9. Open questions

Tracked here so they don't get lost:

- **Section A/B/C dividers in the scroller.** Visual treatment TBD — could be a thin label row (`PRIMARY ⌃` / `SECONDARY ⌃` / `OTHER ⌃`), a sticky sub-header, or just a subtle background shift. Decide when 11.2 starts.
- **CiteChip exact wording.** `[3 mentions]` vs `3 mentions` vs `3·` vs `★ 3`. Pick during 11.2 build, with the operator's eye.
- **Sparkline backend wiring.** 26-week series needs to come from somewhere — either extend `aggregates_aspect_sku` with a `recency_26w` JSON list, or compute in API handler from `mentions.published_at` for the aspect's mention_ids. Compute-at-handler is cheaper now; extend the aggregator if it gets slow.
- **Source coverage display.** 5 dots is the prototype pattern; could also be source marks. Stay with dots for at-rest density; review when 11.2 lands.
- **Long-tail Section C visual weight.** Should Section C rows be muted (smaller text, reduced opacity) to communicate lower priority, or rendered identical to A/B with the section header alone carrying the hierarchy? Decide during build.

---

## 10. Where things live

- Tokens: this file (§2) + `frontend/src/styles/tokens.css` (consumed by Tailwind config).
- Atom components: `frontend/src/components/atoms/`.
- Composite components: `frontend/src/components/<name>.tsx`.
- Pages: `frontend/src/routes/`.
- API contracts they render against: `pulse_check/api/schemas.py`.
- Brief shape: `pulse_check/synthesis/contracts.py` (BriefNarrative).
