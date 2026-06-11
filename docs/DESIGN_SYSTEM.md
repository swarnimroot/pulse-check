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

> **Aspirational, session 39.** These tokens document intent. Today's components use Tailwind's default 4px-grid spacing scale directly (`p-2`, `gap-3`, …); the `--aw-space-*` CSS variables are not declared in `frontend/src/index.css` and are not exposed via `tailwind.config.ts`. Consistency hasn't drifted enough to justify the migration — promote to real CSS vars if/when spacing inconsistency starts showing up in PR review.

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

Wired globally in `frontend/src/index.css` as `*:focus-visible { box-shadow: var(--aw-focus-ring); outline: none; border-radius: 4px; }` — every interactive element inherits the ring on keyboard focus without per-element opt-in. (Patch, session 35 Wave 4 polish.)

### 2.12 Accessibility patterns (Wave 4 polish, session 35)

- **`prefers-reduced-motion: reduce`** zeros all `animation-duration` / `transition-duration` globally (`frontend/src/index.css`). No per-component opt-in needed.
- **Accordions** (Sources, Under the hood) carry `aria-expanded` on the trigger plus `aria-controls` pointing at the disclosed panel's `id`. Trigger is a native `<button>`, so Space/Enter activation comes for free.
- **MultiSelectPopover** (Compare filters, reused on Pair) closes on outside click AND on `Escape` keydown. Both listeners are scoped to `open === true` to avoid global handlers when idle.
- **Icon-only buttons** carry descriptive `aria-label` — `HeatCell` sentiment buttons announce `"Open evidence for <aspect>, N mentions, net sentiment <s>"`; sort headers announce `"Sort by <column>, ascending/descending/unsorted"`.
- **Pair idle state** renders an explainer card with copy `"Pick a product on each side to see the head-to-head comparison."` plus a sub-line describing what loads — replaces the prior `null` return so a stakeholder lands on guidance, not a blank panel.
- **`GlossaryDialog`** (new component, `frontend/src/components/GlossaryDialog.tsx`) — a shared "What are all these numbers?" modal trimmed to **6 entries grouped into 5 sections** (Unit · How we score · How we count · Head-to-head · Output). Trim rationale: drop terms that never appear as labels in the UI (Polarity, Aspect, Verbatim, Citation, Run all dropped or folded into other entries); keep only terms a cold visitor would (a) see on screen AND (b) not guess correctly from context. The "How we count" entry uses sub-bullets (Primary / Secondary / Long-tail side-by-side) since they share a definitional frame. `GlossaryButton` trigger sits at the top-right of every data page header (Standalone landing + product view · Pair · Compare). Closes on outside click and `Escape`. Same content everywhere so vocabulary stays consistent across surfaces.
- **`EvidenceDrawer` verified-only filter hidden** — the underlying `verified_share` aggregate is structurally 0% across the current corpus because no source ingested today (Reddit / YouTube / articles) carries a `verified_purchase` signal. The filter is hidden in the UI until BestBuy + Amazon retailer-review ingestion lands (Wave 2 deferred). Grid layout updated from `grid-cols-2` to `grid-cols-3` so the remaining three filters (source / intensity / recency-disabled) sit on one row.
- **`BriefExportButton`** (new component, `frontend/src/components/BriefExportButton.tsx`) — opens a centered modal previewing a single-page A4 one-pager for the current standalone brief, with PDF (browser-print), HTML (Blob download), and Markdown (Blob download, session 39) export actions in a toolbar above the sheet. Sheet is visual, not text-dump: 4 stat tiles (mentions / pos aspects / neg aspects / avg net) + 11-aspect color-coded chip row + top 3 strengths + top 3 complaints (claim headers only, with bracketed `[n]` cite numbers) + compact citations footer. PDF route adds `body.printing` class → `@media print` rules (`frontend/src/index.css`) hide everything except the `.print-target` sheet so `window.print()` produces a clean A4 file. HTML route serializes `outerHTML` of the sheet into a self-contained `.html` Blob (inline styles throughout, no Tailwind dependency in the saved file). Markdown route emits GFM-flavored text via `frontend/src/lib/exportMarkdown.ts` — snapshot stats table, 11-aspect table, top strengths / complaints bullet lists with bracketed `[n]` cite refs, numbered citations list — citation numbers agree with the visual sheet because both consumers build the same `Map<mention_id, n>` from the same `citedIds` order. Button uses the Variant A soft-tint treatment (`border-accent-soft bg-accent-soft/40`) so it pairs visually with the `GlossaryButton`. Wired into Standalone today; component is generic over `BriefView` + product metadata so it transplants onto a future Pair brief unchanged.
- **`PairBriefExportButton`** (new component, `frontend/src/components/PairBriefExportButton.tsx`, session 43) — comparative-brief sibling of `BriefExportButton`, wired into the Pair page header right of `GlossaryButton` once both products are picked AND a pair brief exists. Same three-route export surface (Save as PDF · Download HTML · Download Markdown) and same A4-preview overlay shape; the sheet content reflects the pair brief: 3 stat tiles (primary leads / ties / competitor leads, X / N format) + two per-product aspect chip rows (11 chips each, same color tones as standalone) + accent contrast block (italic single paragraph, mirrors A1 summary block) + "Where {primary} leads" / "Where {competitor} leads" leader bullets (top 3 per side ranked by abs(delta) above the 0.10 threshold the in-app scorecard uses, each bullet citing up to 2 mention_ids from the leading side) + compact citations footer. Markdown route emits GFM via `frontend/src/lib/pairExportMarkdown.ts` — 3-column snapshot table (primary | competitor), 11-row aspect comparison with Δ column, italic contrast paragraph with `[n]` refs, "Where X leads" bullet lists, numbered citations. Citation numbering is consistent between the visual sheet and the markdown because both consumers walk the same `buildPairCitedIds` ordering (contrast cites → primary leader cites → competitor leader cites, dedup keeping first appearance). Overlay markup is duplicated rather than extracted from `BriefExportButton.tsx` to keep the standalone export untouched; if a third export surface lands later, that's the right moment to extract.
- **`GlossaryButton` highlighted** — Variant A soft-tint (`border-accent-soft bg-accent-soft/40`) so the "What are all these numbers?" trigger reads as a discreet invitation. Matches the Sources accordion treatment on About for consistency.

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

> **Aspirational, session 39.** The line-height and weight token *names* are documented for future consistency. Today the values are wired into `tailwind.config.ts`'s `fontSize` entries as literals (e.g., `lineHeight: "1.45"`), not as `var()` refs, and the `--aw-line-*` / `--aw-weight-*` CSS variables are not declared in `frontend/src/index.css`. Promote to real tokens if/when type-scale churn justifies the migration.

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
| `tombstone` | "link dead" marker on VerbatimCard tag row 2 when `MentionView.tombstoned_at` is set (session 38). Styling: `bg-surface-alt text-fg-muted italic` — muted by design so a dead link doesn't visually compete with live citation signals. |
| `primary` / `secondary` | Attribution-type emphasis on AspectRow / AspectColumn chips (PRIMARY vs SECONDARY attribution). `primary` uses `bg-accent-soft text-accent-hover`; `secondary` uses `bg-surface-alt text-fg-muted`. (Session-39 audit: tones existed in `Chip.tsx` since the §5.1 build; missed by §4.1 inventory until now.) |

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
4. **Tag row 1:** aspect-polarity chip + intensity chip — **for the drilled aspect.** A mention can carry tags for several aspects (a long article verdict often touches performance + thermals + display). When the card renders inside an aspect-scoped drill (heatmap cell, Standalone aspect, Pair cell), it shows the tag for *that* aspect via the `focusAspect` / `focusProductId` props, so the chip's polarity always matches the cell colour the operator clicked. Without a focus (pooled contexts — Pair "Contrast" cites, Showcase fixtures) it falls back to the first tag, which the API returns in canonical `Aspect`-enum order so that "first" is deterministic. **Do not read `aspect_tags[0]` as "the" aspect in an aspect-scoped surface** — that nondeterminism caused a session-44 bug where a negative thermals cell drilled into positive-looking performance/display chips.
5. **Tag row 2 (only if data exists):** `verified purchase` (when present) + `↑ <upvotes>` (Reddit only) + `★ <rating>` (retailer only) + **`link dead`** (session 38; when `MentionView.tombstoned_at !== null` — backed by `scripts/verify_mention_links.py` per ARCH §9).

**Locked exclusions per session-13:** no ownership phrase ("owned 6 months"). The session-13 tombstone-marker lock was lifted in session 38 alongside bite #5 (link-rot / tombstoning).

**EvidenceDrawer is aspect-scoped** (session 44): it threads its `aspect` + `productId` into every card as the focus, and scopes its intensity filter to that aspect too (a "high performance" mention must not survive a "high thermals" filter). The drawer treats focus as active only when a `productId` is supplied — pooled callers (Contrast cites) pass none and get first-tag display.

### 4.9 Skeleton (session 37)

Vanilla content-placeholder block. `<div>` with `animate-pulse rounded bg-muted` (surface-alt §2.1) + a11y attributes (`role="status"`, `aria-busy="true"`, `aria-live="polite"`). Caller sizes + tints per spot via `className`; default tint is `bg-muted`, prominent spots pass `bg-accent-soft` to stay on-brand. Lives at `frontend/src/components/ui/skeleton.tsx`. No new deps — `tailwindcss-animate` was already installed for shadcn primitives.

**Used on (session 37):** Compare heatmap (5 skeleton rows × 11 cells while `/api/compare` loads); Standalone picker (2 stacked dropdown-shaped blocks); Standalone full-page product (title bar + 2 content blocks); Standalone brief panel (heading bar + 4 claim cards each with header + 2 body lines); Pair scorecard (3 count-tile stubs + 6 row stubs); EvidenceDrawer + CitationPanel (3 mention-card stubs each). Replaces the prior text-based "Loading…" copy across all seven spots.

---

## 5. Composite components

### 5.1 AspectRow + AspectColumn (the scroller)

**Locked layout per session-13 + session-16 reaffirm:** two scrollers per Standalone page — left = positive net sentiment, right = negative net sentiment.

**Each scroller has 3 stacked sub-sections, in this order:**

| Sub-section | Contents | Sort |
|---|---|---|
| **Primary** | Top-3 PRIMARY rows (by `total_mentions`) for this polarity | mentions desc |
| **Secondary** | Top-3 SECONDARY rows (by `total_mentions_secondary`), **excluding any aspect already in Primary of this scroller** | mentions desc |
| **Long-tail** | Every other aspect with any mentions in this polarity, **excluding Primary and Secondary of this scroller** | mentions desc |

**No within-scroller repeats.** Cross-scroller divergence is permitted: an aspect with `PRIMARY pos = 0.59` and `SECONDARY neg = −0.18` (real example: rog_strix_g16 price-value) appears in **left scroller's Primary** AND **right scroller's Secondary**. A small `primary` / `secondary` tone chip on the row tells the eye which bucket the metrics represent.

**Column header (always visible):** at the top of the scroll viewport, sticky to the top so it stays visible as the column body scrolls — names the columns `aspect · sentiment · verified · mentions`. Sits inside the scroll viewport (not outside) so its right edge tracks the rows' right edge regardless of scrollbar reservation.

**Row at rest:** `aspect (with bucket chip) · sentiment · verified · mentions`. Single line, ~48px tall. Click → opens EvidenceDrawer with bucket-relevant `mention_ids` (PRIMARY ≠ SECONDARY pool). Intensity column dropped session 16 — too implicit a measure for the operator audience; surface intensity (and SourceDots, Sparkline) inside the EvidenceDrawer or row-expanded state instead.

**Row expanded:** reveals `SourceDots` + `Sparkline` + verbatim preview. Background `--aw-surface-alt`. *(Deferred to a follow-up bite — not in 11.3.a.)*

**Header:** polarity chip with count (e.g., `WHAT IS WORKING (6)` / `COMPLAINTS (5)`). The prior "Positives" / "Negatives" eyebrow text was removed from the prototype mid-iteration; chip-with-count carries the meaning.

**Sub-section dividers (locked session 16):** thin sticky sub-header inside the scroller — `▾ Primary signal` · `▾ Secondary signal` · `▾ Long-tail`. ~24px tall, 11px uppercase tracked, muted text, `--aw-surface-alt` background, single bottom border. Sticky to the top of the scroll viewport so the visible sub-section is always identified as the user scrolls. Chevron is a visual cue only — sub-sections are not collapsible in v1. Empty sub-sections render a one-line muted placeholder (e.g., `No long-tail aspects in this polarity`) so the three-part structure stays legible.

**Scroll behavior (locked session 16, tightened mid-session 16 visual review):** the AspectColumn body has a single outer `max-height` and `overflow-y: auto` — **one scroll cap per column**, not per sub-section. Cap shows roughly **4–5 rows at a time** (~300–340px); anything beyond requires user scroll. Sub-headers stay sticky to the scroll viewport so the user always knows which sub-section is in view. Sized this tight on purpose — the goal is for the brief below to be visible without scrolling the page, with the AspectColumn signaling "more inside, scroll to explore." Long Primary or Long-tail lists don't stretch the column — the user scrolls within. The cap exists so the **BriefPanel below sits at a stable y** regardless of how many aspects any product has.

**Empty state (whole column):** dashed-border card with neutral copy. Right scroller is α-placeholder territory on both pilot products today (zero PRIMARY-backed cons); Secondary (top-3 SECONDARY neg) lifts up immediately.

### 5.2 BriefPanel

**Backend produces 4 quadrants (§6.3); frontend collapses to 2 polarity buckets at render time.** Locked session 15 (operator-driven during the 11.2 Showcase visual confirm — "keep just 2 sections, what's working and what's not working, merge primary and secondary together for up to 5 bullet points"). Backend `briefs.narrative.sections` contract unchanged; the merge is pure render-layer. Implemented session 17 as `frontend/src/components/BriefPanel.tsx`.

| Render section | Merges quadrants | Cap |
|---|---|---|
| `What's working` (positive polarity) | Q1 PRIMARY pos + Q3 SECONDARY pos | up to 5 claims; PRIMARY (Q1) listed first via section order |
| `What's not working` (negative polarity) | Q2 PRIMARY neg + Q4 SECONDARY neg | up to 5 claims; PRIMARY (Q2) listed first; Q2 α-placeholder claim passes through with empty `cited_mention_ids` (renders without `CiteChip`) |

**Section routing key — resolved session 18, bite 11.3.c (fork c).** `bucketBriefByPolarity` reads `narrative.sections[i].heading.toLowerCase()` and routes by substring. Negative keys checked first (the safer mis-classification if a heading combines tokens — surfaces with red dot rather than dropping):

| Polarity | Substrings matched |
|---|---|
| negative | `"not working"`, `"weakness"` |
| positive | `"working"`, `"strength"` |

This catches both fixture headings (`"What's working (PRIMARY)"` / `"What's not working (PRIMARY)"`) and live Sonnet headings on `brief_id=1, 2` (`"High-confidence strengths"` / `"...weaknesses"` / `"Low-signal strengths..."` / `"...weaknesses..."`). Singular substrings (`strength` / `weakness`) catch plural too. Forks (a) positional and (b) prompt-version bump rejected at session 18 in favor of (c) — additive, no cache invalidation, $0 cost.

Each claim renders as a **card** (not a bullet) — `header` (bold, 14px, `--aw-fg`) on its own line, `claim_text` (13px, `--aw-fg-secondary`) below, `CiteChip` inline on the claim line. Cards have a 2px transparent left edge over `--aw-surface-alt` background, 12px horizontal / 8px vertical padding, 12px gap between cards. Older briefs at `a1_brief_v1` (pre-`header`) gracefully render claim_text only.

**Header:** `Brief` eyebrow with `model · prompt_version` suffix · `brief_title` from `narrative.brief_title`.

**Section visual:** h4 with 2px polarity dot prefix (`--aw-success` green for positive · `--aw-danger` red for negative), then card stack as described above.

**Background:** white card with `--aw-shadow-card`, 24px padding, 20px gap between sections.

> **Visual shift, session 33.** Original §5.2 spec (locked sessions 15/17) had a bulleted list with `<strong>header</strong> — claim_text` inline on each bullet. Operator feedback during the 33 visual confirm: inline header was too subtle ("long text death"). Moved to card-per-claim with header on its own line. Backend `Claim` shape unchanged; this is purely a render-layer restyle in `BriefPanel.tsx`.

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

> **Deviation, session 18 — bite 11.3.c.** `atoms/Select.tsx` ships as a styled **native `<select>`** for pilot scale (2 products, 2 brands) rather than the custom click-toggle spec'd above. Tokens align (32px height, accent focus ring, surface border, inline-SVG chevron via background-image + `appearance: none`). Native gives keyboard nav + screen reader support for free. The custom dropdown can land later without changing the `Select` callsite contract (`{label, value, options, onChange}` — same props would back a custom impl). Revisit if option-row meta text (e.g., `2,847 mentions`) becomes a real need.

### 5.7 Cohort toggles

**Hidden v1 per session-13.** Re-add when there's a real workflow demand.

### 5.8 TrendChart (the trend line)

Shipped session 47. Net-sentiment line + mention-volume bars over time buckets — hand-rolled inline SVG (no chart dependency; the §4.7 Sparkline convention at full size). Sentiment on a fixed `[-1, +1]` axis (`--aw-accent` polyline 2px, per-point value-label pills in accent over a `--aw-surface` chip); volume as light bars behind (`--aw-accent-soft` fill + accent hairline). Pure/presentational — props are pre-rolled `{label, net, vol}` buckets. Density-graceful: per-point value labels drop above 18 buckets, volume numbers above 24, x-axis labels thin to ≤26 ticks. The Trend page owns the fetch + the Week/Month/Year rollup (`lib/trendRollup.ts`).

---

## 6. Screen inventory

### 6.1 About (`#/`)

Default landing route. Three-card executive home, locked sessions 32–33.

- Title (h1) "Consumer Voice on Gaming Laptops" + 4-sentence intro paragraph framing the data (aggregates from real public mentions; drillable numbers; briefs cite real mention IDs). Closes with underlined "Refreshed quarterly." cadence note (session 36; supersedes the prior session-31 monthly cadence per quarterly lock).
- **Three product cards** in a row: `Standalone voice` (links to `/standalone` empty-state picker) · `Head-to-head` (links to `/pair`) · `Cross-product heatmap` (links to `/compare`). Each card carries one line of plain-English framing for a non-technical reader. CTA on each card is a **purple-outlined button** (`border-accent bg-surface text-accent`) that flips to **solid purple on hover** (`hover:bg-accent hover:text-fg-on-accent`) — patched session 35 from text-hyperlink-with-arrow to proper button affordance.
- **RunMetaStrip** below the cards: run id · product count · last-refreshed timestamp (live counts from `GET /api/home`).
- **Sources accordion** (accent-soft tinted, sits OUTSIDE the Under-the-hood block): collapsible 3-column table of subreddits + YouTube channels + review sites driven by `GET /api/sources` reading the run + RSS YAMLs at request time.
- **Under-the-hood** collapsible (surface-alt tinted, below Sources): plain-English pipeline explainer + stage counts.

> **Patch, session 34.** §6.1 rewritten to reflect the shipped 3-card home; supersedes the session-13 "Standalone selector + Compare placeholder" two-card spec.

### 6.2 Standalone (`#/standalone[/:productId]`)

A1 product voice page. Locked layout per session-13, refined session 33.

1. RunMetaStrip
2. Header strip: `Home` back button · `A1 · Standalone voice` eyebrow · selector (right-aligned).
3. Sub-header: product name h1 · `<n> mentions · <window>` (drillable count opens drawer with all mention_ids).
4. **Two-column scroller:** §5.1 — left positive | right negative. Each column has Primary / Secondary / Long-tail sub-sections (sticky sub-headers) inside one scroll viewport per column; max-height anchors the BriefPanel below at a stable y across all products.
5. **BriefPanel:** §5.2 — card-per-claim render with header on its own line + claim_text below.
6. **Header actions cluster (top-right, session 35):** `What are all these numbers?` glossary trigger pill + `Export brief` trigger pill (visible only when a brief is loaded). Both use soft-lavender tint (`border-accent-soft bg-accent-soft text-accent`). Export opens a centered overlay with a single-page A4 preview (4 stat tiles + 11-aspect color-coded chip row + top 3 strengths + top 3 complaints + citations footer) and three actions: Save as PDF (browser `window.print()` with `@media print` rules hiding everything except the sheet), Download HTML (Blob download with inlined styles, self-contained), and Download Markdown (Blob download of a GFM brief — added session 39 for paste-into-doc workflows). Overlay uses `backdrop-blur-md` to defocus page content behind it.

Empty state when no `productId` in route (or `/standalone` itself): Company → Product picker card. **No default product is auto-selected** on landing or on Company-change — visitor must explicitly pick a product before any content renders (operator-locked, session 33).

### 6.3 Compare (`#/compare`) — cross-product aspect heatmap

Shipped session 32, polished sessions 33–34. Rows = products (Alienware pinned by default, 2px purple left edge as a row marker), cols = 11 aspects in canonical order + a sticky `Company` column (130px) + sticky `Product` column (200px). Cell tint per §2.5 net-sentiment polarity (`success-soft` / `warning-soft` / `danger-soft`); cell number = mention count. Click any cell to open the `EvidenceDrawer` scoped to that (product, aspect).

Auto-populate semantics: `GET /api/compare` once on mount; refresh the tab to pick up new aggregates as Stage B fills in. No polling.

**FilterPanel** (above the grid): three `MultiSelectPopover`s — `Company` · `Screen size` · `Product`. All default to **all-selected**.

> **Cascading filters, session 34.** Downstream popovers narrow to what's reachable under upstream selections. Changing `Company` auto-rebases `Size` and `Product` to "all available under the current company set"; changing `Size` auto-rebases `Product`. Product is the leaf — narrowing it does not cascade. Trade-off: user-pinned narrowings in `Size` / `Product` are wiped when an upstream filter changes.

> **Screen-size regex, session 34.** `(?<!\d)(13|14|15|16|17|18)(?!\d)` — accepts model suffixes/prefixes (`16x`, `16s`, `Z13`, `X16`) while rejecting adjacent-digit false positives (`160`, `1314`). Products with no derivable size (`Legion 7 (AMD, non-Pro)`, `Legion 7i`, `Legion 9i`) always pass the size filter rather than being silently dropped.

**Legend** (between FilterPanel and the grid, session 34): three sentiment swatches (positive / mixed-neutral / negative) + Alienware purple-edge marker + inline action hints (`cell = mention count · click cell to drill into verbatims · click any column header to sort`).

**Sortable columns, session 34.** Click any aspect header to sort products by that aspect's net_sentiment; click the `Company` header to sort alphabetically by brand. Click cycle: asc → desc → clear (third click restores the brand-grouped Alienware-pinned default). Cells with no mentions sentinel-park at the bottom regardless of direction. Active sort header tints `--aw-accent` and shows ▲ / ▼.

**Row-hover affordance, session 34.** Each product row wraps its cells in a `display: contents` group so `:hover` on any cell dims the entire row's cells (`group-hover:brightness-[0.97]`) and underlines the product name — helps the eye read across one product's aspects on a wide grid.

### 6.4 Pair (`#/pair`) — head-to-head A1 comparison

Shipped session 32, redesigned session 33. Two `PickerColumn` sides — no auto-pick on landing; visitor explicitly picks Company → Product on each side.

`PairScorecard` body: three `CountTile`s (`Primary leads N` / `Ties N` / `Competitor leads N`) above a single combined `PairTable` sorted by combined `total_mentions` (talked-about signal; tiebreaker = canonical aspect order). Each row: `[P1 score | Aspect | P2 score]`. `PairCellChip` on the leader column gets a 2px accent ring (`ring-2 ring-accent ring-offset-1`).

### 6.5 Trend (`#/trend`) — per-aspect sentiment over time

Shipped session 47. Wave 6 follow-on to the daily-ingestion trend read path. Header: a single `Select` pair (Company → Product) — no auto-pick, same cascade pattern as Pair/Standalone. Once a product is chosen, fetches `GET /api/trend/{product_id}` (weekly snapshots only) and renders one aspect at a time: aspect-picker chips + a **Week / Month / Year** segmented toggle above a `TrendChart` (§5.8). Month/Year roll the weekly snapshots up client-side (volume summed, net sentiment volume-weighted — faithful to "every mention = 1.0"). Summary row below: latest net · latest volume · period-over-period delta. Empty-state when the product has no weekly snapshots yet (pre-cron only the pilot run exists, which the endpoint filters out); explicit single-point note when exactly one. No evidence drill — trend points carry no `mention_ids`.

### 6.6 Showcase (dev-only QA route)

`frontend/src/pages/Showcase.tsx` — visual-QA page rendering every atom and composite against fixture data. Not wired into the production navigation; reachable only by manually loading `#/showcase` during frontend development. Kept in-tree so a designer can eyeball every atom/composite without spinning up the full pipeline. (Session-39 audit: noted in §6 inventory after missing from §6.1–§6.4 since session 32 introduction.)

### 6.7 WelcomeModal (overlay on `#/` fresh visits)

`frontend/src/components/WelcomeModal.tsx` — overlay shown on every fresh App mount that lands on `#/`. In-app navigation does NOT re-trigger; state is captured once via `useState(() => location.pathname === "/")` in `App.tsx`. F5 / new tab / direct URL re-mounts App and re-opens.

Layout: white card on `bg-fg/40 backdrop-blur-md` scrim, max-width `3xl`. Header carries the `pulse-check` eyebrow + "At a glance" title + close `X`. Body is a `grid-cols-3` of three sections — `AlertCircle` / `Sparkles` / `Users` lucide icons + eyebrow + 1-line body + inline SVG diagram (scattered sources → faded "?", funnel mentions → 11 aspect bars → brief card, 4-persona row with "quarterly cadence" caption). A `bg-surface-alt/40` band below carries "How each function uses it" with 4 purple-pill rows (PM / Mkt / Eng / Sales) + one-line use cases. Footer is a single `bg-accent` Got-it CTA.

Dismissal — all four routes call the same `onClose`: X button (top-right), backdrop click (with `stopPropagation` on the inner card so content clicks don't dismiss), Escape keydown (document listener), Got-it CTA. (Session-40 addition. Operator-confirmed lock: shows on every fresh page-load of `/` — `localStorage`/`sessionStorage` deliberately not used.)

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

- ~~**Section A/B/C dividers in the scroller.**~~ **Resolved session 16** — sticky sub-headers `▾ Primary signal` / `▾ Secondary signal` / `▾ Long-tail`; one outer scroll cap per column. See §5.1.
- **CiteChip exact wording.** `[3 mentions]` vs `3 mentions` vs `3·` vs `★ 3`. Pick during 11.3 build, with the operator's eye.
- **Sparkline backend wiring.** 26-week series needs to come from somewhere — either extend `aggregates_aspect_sku` with a `recency_26w` JSON list, or compute in API handler from `mentions.published_at` for the aspect's mention_ids. Compute-at-handler is cheaper now; extend the aggregator if it gets slow.
- **Source coverage display.** 5 dots is the prototype pattern; could also be source marks. Stay with dots for at-rest density; review when 11.3 lands.
- **Long-tail visual weight.** Should Long-tail rows be muted (smaller text, reduced opacity) to communicate lower priority, or rendered identical to Primary/Secondary with the sub-header alone carrying the hierarchy? Decide during 11.3 build.

---

## 10. Where things live

- Tokens: this file (§2) + `frontend/src/styles/tokens.css` (consumed by Tailwind config).
- Atom components: `frontend/src/components/atoms/`.
- Composite components: `frontend/src/components/<name>.tsx`.
- Pages: `frontend/src/routes/`.
- API contracts they render against: `pulse_check/api/schemas.py`.
- Brief shape: `pulse_check/synthesis/contracts.py` (BriefNarrative).
