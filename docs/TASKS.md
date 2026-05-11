# pulse-check — Tasks

**Status:** draft &nbsp;·&nbsp; **Paired docs:** [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`TESTING.md`](TESTING.md) &nbsp;·&nbsp; **Last reconciled:** 2026-05-11 (session 18 — bite 11.3.c close, awaiting operator visual smoke for 11.3.d)

Wave-by-wave implementation plan matching the PRD's ~7–8 week single-operator estimate. Each wave has clear outputs, specific tasks, dependencies, and exit criteria. **Wave 2 is the A1-only cutpoint** — if v1 slips, A1 alone is a defensible ship.

---

## Current bite

Live tracker — updated immediately on bite start, sub-bite close, deviation, or bite close (per `CLAUDE.md` doc-evolution clause 5). Sub-bites also land in their wave section so history persists when the active bite rotates.

**Active:** 11.3 — frontend pages + live wiring. **11.3.0 prelude + 11.3.a AspectColumn refactor closed in session 16. 11.3.b pages + hash router closed in session 17. 11.3.c selectors + live API wiring closed in session 18 (293 backend tests pass; mypy/ruff/tsc clean; live endpoints curl-verified end-to-end). Next: 11.3.d — operator visual smoke against live DB.**

- [x] 11.3.c.1 — Backend: added `latest_brief_id: int | None` to `ProductDetail` schema + handler (`_latest_a1_brief_id_for_product` selects MAX(brief_id) WHERE `scope_type=aspect_1_sku` AND `scope_id=product_id`). Three test cases added/updated in `tests/unit/api/test_app.py`: ready product asserts `latest_brief_id is None` when no brief seeded; empty-aspects product also asserts None; new `test_product_detail_advertises_latest_a1_brief_id` seeds two A1 briefs on the target product + one on a sibling product, asserts MAX wins + no cross-product bleed. **Deviation flagged** — adds one field to `/api/product/:id` response. *(session 18)*
- [x] 11.3.c.2 — Frontend types: `ProductDetail.latest_brief_id: number | null` mirrors backend; fixture `sampleProduct` sets it to `1`. *(session 18)*
- [x] 11.3.c.3 — `BriefPanel.bucketBriefByPolarity` keyword set extended to also match `"weakness"` / `"strength"` substrings (singular catches both singular and plural). Negative check runs first so combined-token headings would route to negative (the safer mis-classification — red dot rather than dropped claim). Live curl confirmed brief 1/2 headings (`"High-confidence strengths"` / `"...weaknesses"` / `"Low-signal strengths..."` / `"...weaknesses..."`) all route correctly. *(session 18)*
- [x] 11.3.c.4 — `frontend/src/lib/api.ts` rewritten: kept `apiFetch` + `ApiError` + `BASE_URL`; replaced route helpers with typed `products()` → `ProductsResponse`, `productById(id)` → `ProductDetail`, `brief(id)` → `BriefView`, `mentions(ids: string[])` → `MentionsResponse` (short-circuits empty array client-side). Dropped `pairs()` Wave 1 stub. *(session 18)*
- [x] 11.3.c.5 — `frontend/src/components/atoms/Select.tsx`: native-`<select>` wrapper, 32px height, accent focus ring, inline-SVG chevron via background-image with `appearance: none`. **Deviation flagged** — DESIGN_SYSTEM §5.6 mandates a custom (non-native) dropdown; native used here for pilot scale. Exported via barrel. *(session 18)*
- [x] 11.3.c.6 — `pages/About.tsx` rewrite: fetches `/api/products` on mount; renders two dependent Selects (Company by `brand`, Product by `display_name`) + `Open standalone →` button that navigates to `/standalone/:productId`. Auto-selects first company + product on load so single-click open works. Loading: muted "Loading…". Error: card with `retry` button (bumps `reloadKey`). Empty list: italic muted note. *(session 18)*
- [x] 11.3.c.7 — `pages/Standalone.tsx` rewrite: state machine `ProductState` (loading / notFound / error / ready) + `BriefState` (idle / loading / error / missing / ready). Product fetch keyed on `[productId, productReloadKey]`; 404 ApiError → notFound branch. Brief fetch fires when product is ready AND `latest_brief_id !== null`. Mentions fetched lazily: drawer/citation open optimistically with `loading=true`, fetch resolves into the same panel only if it's still the active one (stale-guard on aspect / claimText). All hooks declared before any early return — rules-of-hooks preserved. *(session 18)*
- [x] 11.3.c.8 — `EvidenceDrawer` + `CitationPanel` extended with optional `loading?: boolean` + `errorMessage?: string | null` props; when set, the body region renders muted "Loading…" or red-toned error line instead of the empty/filter-empty state. Backward-compatible with Showcase (passes neither). *(session 18)*
- [x] 11.3.c.9 — **Pre-existing Wave 1 bug fix surfaced by smoke.** `frontend/src/lib/api.ts` used `??` to fall back BASE_URL to `"./api"`, but `.env.production` sets `VITE_API_URL=` (empty string) and `??` only triggers on null/undefined — leaving BASE_URL as `""`, so every fetch hit `/products` (etc.) instead of `/api/products`, got caught by the SPA fallback, returned `<!doctype …>`, and `JSON.parse` threw. Bug existed since the Wave 1 stub but was first exercised end-to-end in this bite. One-char fix: `??` → `||`, with an explanatory comment. *(session 18 — surfaced by 11.3.d smoke)*

- [x] 11.3.0 — DESIGN_SYSTEM §5.1/§6.2/§9 reconciliation. §5.1 AspectColumn block locks the 3 sub-sections as **Primary / Secondary / Long-tail** (concrete names replacing abstract A/B/C); sticky sub-headers `▾ Primary signal` / `▾ Secondary signal` / `▾ Long-tail` (24px, 11px uppercase tracked, muted, sticky to scroll viewport, chevron is visual only — non-collapsible v1); empty sub-section renders one-line muted placeholder. **Scroll mechanics locked: one outer scroll cap per column** (max-height ~440–480px target; exact px a 11.3 build-time call), sized so the polarity chip + Primary fully visible + Secondary sub-header peeks above the fold — anchors BriefPanel below at a stable y. §6.2 Standalone updated to reference Primary/Secondary/Long-tail. §9 open question on dividers struck through (resolved); long-tail visual-weight question renamed; `11.2 build` references updated to `11.3 build`. *(session 16)*
- [x] 11.3.a — AspectColumn 3-section partition + outer column scroll cap + sticky sub-headers + bucket-tone chip. New atom `frontend/src/components/atoms/AspectRow.tsx` (single-line at-rest row, takes `bucket: 'primary' | 'secondary'` and renders bucket-relevant metrics); new composite `frontend/src/components/AspectColumn.tsx` (deterministic `partitionAspects(aspects, polarity)` honoring cross-scroller divergence — left col Primary uses `total_mentions/net_sentiment`, left col Secondary uses `total_mentions_secondary/net_sentiment_secondary` excluding aspects already in Primary; long-tail uses PRIMARY-precedence to pick which bucket's metrics to show); `Chip.tsx` extended with `primary` (accent-soft) and `secondary` (surface-alt) tones; `Showcase.tsx` deletes the inline flat-list `AspectColumn`, imports the new composite, and updates the click-handler to `(row, bucket) => openDrawer(row.aspect, bucket === 'primary' ? row.mention_ids : row.mention_ids_secondary)`; `fixtures/sample.ts` extended from 6 → 10 aspects so all three sub-sections fire in BOTH columns + `build_quality` demonstrates cross-scroller divergence (left-Primary at PRIMARY +0.62 / right-Secondary at SECONDARY −0.18). `tsc -b --noEmit` clean. **Deferrals flagged:** row expand-on-click, IntensityBar/SourceDots/Sparkline inside row at-rest (only in expanded state), sub-section collapse interaction (chevron is visual-only v1). *(session 16)*

**Closed in session 15:**
- [x] 11.2.a — Light-theme token swap (`frontend/src/index.css` rewritten with `--aw-*` tokens from DESIGN_SYSTEM §2 verbatim; `tailwind.config.ts` updated to read new var names + light-theme fontSize/borderRadius scales; shadcn semantic aliases preserved)
- [x] 11.2.b — Atoms: Chip, DrillNumber, CiteChip, SourceMark, SourceDots, IntensityBar, Sparkline, VerbatimCard (all in `frontend/src/components/atoms/` + barrel index; types mirrored from `pulse_check/api/schemas.py` in `frontend/src/lib/types.ts`)
- [x] 11.2.c — Composites: EvidenceDrawer (440px, 4 filters with recency disabled per v1), CitationPanel (380px, `offsetForDrawer` prop pushes to right=440 when drawer co-open), RunMetaStrip (non-jargon: total mentions · window · last refreshed)
- [x] 11.2.d — Dropped Exo 2 + Rajdhani Google Font links from `frontend/index.html`. **Deviation:** Inter `<link>` block also dropped + body font-family set to system stack per DESIGN_SYSTEM §3.1 (Arial Nova → Arial → Helvetica). `class="dark"` removed from `<html>`; `color-scheme` flipped to `light`. Flag for operator: scope was literally Exo 2 + Rajdhani; Inter removal aligns with §3.1 spec but expanded actual scope.
- [x] 11.2.e — Fixtures (`frontend/src/fixtures/sample.ts`: 12 mentions × 5 source types, 6 AspectRows, 1 BriefView, 1 RunMeta) + `Showcase` page wired at `/showcase` rendering every atom + composite. TS clean (`tsc -b --noEmit` passes); dev server boots.

**Carryover into 11.3 implementation:**
- **AspectColumn 3-section partition gap.** 11.2 shipped a flat `<ul>` per column with no sub-section partition, no `total_mentions_secondary` use, and no scroll cap. 11.3.a must implement the §5.1-locked structure: top-3 PRIMARY / top-3 SECONDARY (excluding Primary aspects) / Long-tail (rest) per polarity column, with sticky sub-headers + outer column max-height + cross-scroller divergence preserved + a `primary`/`secondary` row-tone chip indicating which bucket the displayed metrics represent.
- Existing `Landing` / `Product` / `Pair` pages still reference dead Tailwind classes from the dark scaffold (`bg-surface-0`, `text-text-primary`, `font-display`, `text-display`, etc.). Tailwind silently no-ops on these so the build is clean, but the placeholders render unstyled. 11.3 rebuilds them anyway — leaving as-is for now.
- Sparkline accepts arbitrary `data: number[]`. 26-week recency series isn't materialized in `aggregates_aspect_sku.by_recency`; 11.3 derives it at API-handler time from `mentions.published_at` for each aspect's `mention_ids`.
- DESIGN_SYSTEM §3.1 vs HTML reconciliation: §3.1 specifies system stack only; 11.2.d cleanup completes that pivot in the HTML. Already aligned post-bite — no doc edit needed.

**Blocked / waiting on operator:**
- [ ] 6.3 — YouTube end-to-end (operator URL curation pending)
- [ ] 6.4 (deferred) — BestBuy + Amazon retailer reviews (three open plumbing items; see Wave 2 → Scraping enrichment)

**Next:** 11.3 — frontend pages + live wiring (depends on 11.2)

---

## Parallel prerequisite (week 0 / ongoing)

Operator-side setup that runs alongside code work. Not blocking for Wave 1 start.

- [x] Install Python 3.12 + create `.venv`
- [ ] Install Ollama + pull `qwen2.5:7b-q4_K_M` (or operator's preferred Qwen tag); verify local LLM works *(operator-side; aspect tagging swapped to Haiku in session 5 — Ollama+Qwen still scoped for Wave 3 deliberation/reason classifiers)*
- [x] Get Anthropic API key; store in `.env`
- [x] Install scrapers-lib editable from sibling directory (`pip install -e ../scrapers-lib`)
- [ ] `playwright install chromium` (for scrapers-lib Tier 2/3 sources)
- [ ] Curate **YouTube seed list** — ~10–15 videos per demo pair (head-to-heads + expert single-product reviews). Target: ~50–75 URLs total for the 10-pair demo.
- [ ] Curate **article seed list** — ~20–30 articles per pair (roundups + reviews + head-to-heads). Target: ~150–200 URLs.

Seed-list curation is the biggest operator-side time cost outside coding. Start early.

---

## Wave 1 — Foundation (weeks 1–2)

**Goal:** the shared layer is working. Can scrape, attribute, store, cache. Frontend/backend shells exist. Ready for aspect work.

**Status:** ✅ complete (session 5).

**Exit criteria:**
- `alembic upgrade head` creates a full schema matching ARCHITECTURE §3
- `scripts/scrape.py --run-config configs/run_smoke.yaml` runs end-to-end on a 2-product smoke test
- Unified corpus in SQLite shows mentions from all 5 source types with correct primary + secondary attribution
- LLM cache table populated; repeat calls hit cache
- FastAPI + React scaffolds both run locally; "hello world" page loads

### Tasks

**Scaffold**
- [x] `pyproject.toml` — package metadata, dependencies, entry points
- [x] `.env.example` — documented credential template
- [x] `.gitignore` — `data/`, `.venv/`, `.env`, `__pycache__/`, `node_modules/`, `dist/`, `alembic/versions/*.pyc`
- [x] `git init` (locally, no push); initial commit after scaffold lands
- [x] pre-commit config — ruff, mypy, fast-unit test subset
- [x] `pytest` config in `pyproject.toml`; `tests/` tree with `unit/`, `integration/`, `eval/` subdirs
- [x] Logging config — stdlib logging with a rotating file handler pointing at `data/pulse_check.log`

**Storage**
- [x] SQLAlchemy setup — engine, session factory, declarative base
- [x] Alembic init — `alembic.ini`, `alembic/env.py`, first migration covering all tables in ARCHITECTURE §3
- [x] Storage helpers — session context manager, basic CRUD wrappers
- [x] Unit tests on each model: constraint enforcement, timezone round-trip, JSON column round-trip

**Config**
- [x] Pydantic v2 models — `ProductSet`, `PairPlan`, `RunConfig`, `SourceWindows`
- [x] YAML loader with validation; clear errors on malformed input
- [x] Example configs in `configs/` — a `smoke_test.yaml` (2 products) + placeholders for the demo run (7 products, filled in at Wave 5)
- [x] Unit tests on validation (happy + edge cases)

**Scrapers-lib integration**
- [x] Wrapper module per source — Reddit, BestBuy reviews, Amazon PDP, YouTube, article — converts `RawMention` / `ProductSnapshot` to `Mention` rows
- [x] Scheduler wiring — drive all fetchers via `scrapers_lib.Scheduler` for resumability
- [x] Primary attribution at fetch time via `attribute_regex_all`
- [x] Secondary attribution pass — post-fetch sweep over all mentions' raw text against all product patterns

**LLM infrastructure**
- [x] `llm_cache` table + wrapper — `call_with_cache(task, input_payload, prompt_version, model, temperature)`
- [x] Ollama client wrapper — JSON-output mode, retry on parse failure, consistent error types
- [x] Anthropic client wrapper (Sonnet + Haiku) — structured output, retry, error types
- [x] Unit tests on cache (hit/miss/versioning) + mocked LLM clients

**Frontend + backend shells**
- [x] Vite + React + TS project in `frontend/`
- [x] Tailwind + shadcn/ui setup with tokens from DESIGN_SYSTEM §3 *(Tailwind + tokens configured; shadcn deps installed; individual components are generated on-demand under Wave 2/4 frontend tasks)*
- [x] Basic router (`/`, `/product/:id`, `/pair/:id`)
- [x] API client skeleton
- [x] FastAPI app with CORS + error middleware; routes for `/health`, stubs for `/products`, `/pairs`
- [x] Run scripts — `scripts/serve.py` launches backend + frontend dev server

---

## Wave 2 — Aspect 1 (week 3) — **A1-only cutpoint**

**Goal:** full A1 scorecard view for a given product; classifier passes its gold-set threshold.

**Status:** ~98% complete. Tagging + gold-set build + A1 aggregation done on real corpus (session 5). Content-type pre-classifier + tag-time gate (session 6, bite 6.1). Reddit-deepen via comment inheritance (session 8, bite 6.2-revised) — corpus 33 → 1143 mentions; aspect_tags 95 → 649. **Option 3 — A1 aggregate PRIMARY/SECONDARY column split — DONE (session 9, alembic `b8560c93bbd8`).** **Synthesis package skeleton + §6.3 BriefNarrative Pydantic contracts (session 10, bite 10.1)** + **Haiku near-duplicate dedup with cache + validation (session 10, bite 10.2)**. **Deterministic verbatim selector + Sonnet four-quadrant brief writer + ARCHITECTURE §6.3 A1 layout lock (session 11, bite 10.3).** **Citation validator + retry loop + `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI + first live Haiku+Sonnet smoke on both pilot products (session 12, bite 10.4).** **Backend API handlers (`/products`, `/product/:id`, `/mentions?ids=`, `/brief/:id`) + Pydantic schemas + 21 handler tests + DESIGN_SYSTEM full rewrite (session 13, bite 11.1).** Eval runner, frontend atoms (11.2), and pages + live wiring (11.3) remain.

**Deviation flags (all approved + folded into ARCHITECTURE in session 9):**
- ~~**Session 5:** aspect classifier swapped Qwen 7B → Haiku.~~ Folded into ARCHITECTURE §6.1 (deviation note pointing at §6.5) + §6.5 (Haiku batch classifiers table).
- ~~**Session 6:** Haiku content-type pre-classifier + `--exclude-content-types` gate.~~ Folded into ARCHITECTURE §6.5.
- ~~**Session 8:** comment-inheritance tertiary attribution.~~ Folded into ARCHITECTURE §5 (third paragraph).
- ~~**Session 8 (locked, queued):** Option 3 dual-track aggregate.~~ Implemented (session 9). ARCHITECTURE §3.3 + §7.1 updated for the dual-bucket schema + algorithm.

**Exit criteria:**
- Aspect + polarity + intensity classifier reaches ≥ 80% accuracy on the aspect_tagging gold set
- `/product/:product_id` renders the full scorecard (AspectRow × 11, BriefPanel) with drillable numbers and working EvidenceDrawer
- One end-to-end demo product produces a plausible, citation-validated A1 brief
- Re-running the full pipeline produces byte-identical aggregate + brief output (LLM cache hits)

**If v1 timeline slips: this is where you ship. A1 alone is defensible.**

### Tasks

**Tagging**
- [x] Qwen → **Haiku** aspect + polarity + intensity classifier — prompt + JSON schema + anchor examples per aspect *(provider swap landed in session 5)*
- [x] Batch runner — iterate mentions in the corpus, call Qwen via the cached wrapper, write `aspect_tags` rows
- [x] Snapshot test on prompt string
- [x] Content-type pre-classifier (Haiku, `review|deal|other`) + `--exclude-content-types` gate on aspect-tag batch *(session 6, bite 6.1)*
- [x] Within-response aspect dedup in `parse_response` *(session 8, fixes UNIQUE-constraint crash on Haiku occasional dupes)*

**Scraping enrichment**
- [x] Reddit comment fetcher integration with `emit_all_comments=True` bypass (orchestrator extension; scrapers-lib kwarg added) *(session 8, bite 6.2-revised round 1+2)*
- [x] Comment inheritance — parent-post PRIMARY → comment SECONDARY via `metadata_["parent_id"]` lookup *(session 8, `apply_comment_inheritance` post-fetch step)*
- [ ] Bite 6.4 (deferred) — BestBuy + Amazon retailer reviews path. Three open plumbing items: BestBuy network/Akamai timeout; pulse-check `result_sink` mapping for `('amazon','post')` and `('bestbuy','post')`; Amazon Strix empty-review-page diagnosis.

**Gold set + eval**
- [x] `scripts/build-gold-set.py --task aspect_tagging` — Sonnet labels ~150 sampled mentions *(28-entry gold set built on real corpus; below the 150 target — sample size to revisit when corpus grows)*
- [x] `scripts/review-gold-set.py` — CLI helper for the operator's 20–30-sample spot-check (accept/flag/correct)
- [ ] `scripts/run-eval.py --task aspect_tagging` — Qwen vs. gold set, accuracy table, confusion matrix
- [ ] Iterate classifier prompt until ≥ 80% on the gold set

**Aggregation**
- [x] A1 aggregator — per `(run, product, aspect)` compute `aggregates_aspect_sku` rows with `mention_ids` provenance
- [x] Unit tests — invariants (sum of polarity counts == total; provenance matches mentions)
- [x] **Option 3 — A1 aggregate PRIMARY/SECONDARY split** — alembic `b8560c93bbd8` adds 8 `*_secondary` columns; `aggregate_a1` partitions tags PRIMARY vs SECONDARY-only (PRIMARY precedence on dual-attributed pairs), runs the 8-field arithmetic twice. ARCHITECTURE §3.3 (table + intro) + §5 (tertiary paragraph) + §6.1/§6.5 (Haiku deviations) + §7.1 (algorithm) updated. `preview_brief.py` adds sidebar + strict-isolation filter. 17 a1 tests (was 12). Live rerun: 18 → 22 rows; PRIMARY 71 preserved, SECONDARY 578 newly visible. *(session 9)*

**Synthesis**
- [x] Synthesis package skeleton + §6.3 brief contracts — `pulse_check/synthesis/contracts.py` (`Claim`, `BriefSection`, `BriefNarrative`, `NumericalDrift`, `ValidationResult`); skeleton modules `dedup`/`selector`/`brief_writer`/`citation_validator`/`orchestrator`. `BriefNarrative.model_dump()` round-trips through `briefs.narrative` JSON column. *(session 10, bite 10.1)*
- [x] Haiku near-duplicate clusterer — `cluster_near_duplicates(session, mentions, *, client) -> dict[str, str]` with `call_with_cache` + edge-case short-circuits + input/output mention_id validation + opaque cluster_id normalization. 9 mocked-client tests. *(session 10, bite 10.2)*
- [x] Deterministic verbatim selector — returns IDs only; per (polarity, bucket) ranks `aspect_tags.intensity` desc, dedups by cluster, caps at 3. `select_a1_verbatims(...) -> AspectSelection` (4-tuple per polarity × bucket). NEUTRAL never cited. **No LLM call.** 9 tests. *(session 11, bite 10.3)*
- [x] Sonnet A1 brief writer with citation contract per ARCHITECTURE §6.3 — `write_a1_brief(...) -> BriefNarrative`. Pure-Python four-quadrant routing (Q1 PRIMARY pos ≥3 / Q2 PRIMARY neg ≥3 / Q3 SECONDARY pos ≥1 not in Q1 / Q4 SECONDARY neg ≥1 not in Q2); Sonnet writes only `brief_title` + per-(quadrant, aspect) `claim_text`. Empty Q2 always renders α placeholder. All-quadrants-empty short-circuits Sonnet. `Claim.cited_mention_ids` constraint relaxed to `min_length=0` for the placeholder claim. 9 tests (mocked client). *(session 11, bite 10.3)*
- [x] Citation validator — `validate_citations(session, *, narrative, aggregates, allowed_pool, drift_tolerance) -> ValidationResult`. Four soft-warn checks (fabricated_ids / out_of_context_ids / numerical_drift via `\d+\s+(user|mention|thread|...)` pattern / empty_claims with §6.3 placeholder exempt). 11 tests. *(session 12, bite 10.4)*
- [x] `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI — load aggregates → Haiku dedup PRIMARY pool → loop selector per aspect → brief writer → validator → on `fabricated_ids` retry once with `prompt_version = a1_brief_v1_strict` → persist `Brief` row with `flagged_citation_issues` injected as top-level key on `briefs.narrative` JSON. 7 tests. *(session 12, bite 10.4)*
- [x] First live Haiku + Sonnet smoke — `brief_id=1` (alienware_16_aurora) + `brief_id=2` (rog_strix_g16) persisted; both 4-section briefs (Q2 α placeholder on both — 0 PRIMARY-neg ≥3 aspects on either product per current corpus); validator clean (0 fabricated / 0 out-of-context / 0 drift / 0 empty), no retry fired; ~$0.50 spend. *(session 12, bite 10.4)*
- [ ] Integration test — end-to-end brief generation on fixture corpus *(deferred — orchestrator is covered by 7 unit tests against in-memory SQLite; full integration test against `data/pulse_check.db` is Wave 4 work)*

**API**
- [x] `/products` — list products in current run *(session 13, bite 11.1)*
- [x] `/product/:id` — scorecard data (aspects + aggregates + brief) — `_latest_run_id_for_product` queries `aggregates_aspect_sku.computed_at` desc since `runs` table is empty in live DB *(session 13, bite 11.1)*
- [x] `/mentions?ids=...` — resolve mention_ids to full cards; CSV ids, 500-id batch cap, preserves caller order, drops unknowns silently *(session 13, bite 11.1)*
- [x] `/brief/:id` — single brief with citations; passes through `briefs.narrative` JSON unchanged with `flagged_citation_issues` riding along as a top-level key *(session 13, bite 11.1)*

**Frontend — bite 11.2 (atoms + drawer, fixture-only; no live wiring)** *(session 15 — closed)*
- [x] Light-theme token swap — `frontend/src/index.css` + `frontend/tailwind.config.ts` rewritten to `--aw-*` tokens per DESIGN_SYSTEM §2 verbatim
- [x] Atoms: Chip (14 tones), DrillNumber, CiteChip (per-claim, not numbered, tooltip + click-to-pin), SourceMark (5 sources, prefix-normalized), SourceDots, IntensityBar, Sparkline, VerbatimCard (no ownership/tombstone fields per session-13 lock)
- [x] Composites: EvidenceDrawer (440px, source/verified/recency-disabled/intensity filters, Esc closes, page interactive), CitationPanel (380px, `offsetForDrawer` prop), RunMetaStrip (non-jargon labels)
- [x] Dropped Exo 2 + Rajdhani Google Font links. **Deviation flagged:** Inter link also dropped + body font-family set to system stack per DESIGN_SYSTEM §3.1; `class="dark"` removed; `color-scheme` flipped to `light`.
- [x] Showcase page (`frontend/src/pages/Showcase.tsx`) wired at `/showcase`; renders all atoms + composites against fixture data (`frontend/src/fixtures/sample.ts` — 12 mentions × 5 source types, 6 AspectRows, 1 BriefView). TS clean; dev server boots; operator visual confirm pending.

**Frontend — bite 11.3 (pages + live wiring; depends on 11.2)**
- [x] 11.3.0 — DESIGN_SYSTEM §5.1/§6.2/§9 reconciliation: 3-section AspectColumn (Primary/Secondary/Long-tail) + per-column scroll cap + sticky sub-headers locked. *(session 16)*
- [x] 11.3.a — AspectColumn refactor: new `atoms/AspectRow.tsx` + new `components/AspectColumn.tsx` (deterministic `partitionAspects` with cross-scroller divergence honored); Chip tones extended (`primary`/`secondary`); Showcase swaps inline flat-list for the new composite + bucket-aware drawer click; fixtures extended 6 → 10 aspects to exercise all three sub-sections in both columns + a divergence example. TS strict clean. **Awaiting operator visual confirm on `/#/showcase`.** *(session 16)*
- [x] 11.3.b — Pages: About (lean), Standalone, Compare (placeholder, "Wave 3 — coming soon"); hash router `#/`, `#/standalone/:productId`, `#/compare` *(session 17 — code shipped, tsc clean, awaiting operator visual confirm before 11.3.c)*
  - [x] 11.3.b.1 — Route table swap (`App.tsx`); deleted dead `Landing.tsx` / `Product.tsx` / `Pair.tsx`
  - [x] 11.3.b.2 — `pages/About.tsx` lean shell with static product link list (live dropdown deferred to 11.3.c)
  - [x] 11.3.b.3 — `pages/Standalone.tsx` (reads `:productId`, "product not found" empty state) + extracted `components/BriefPanel.tsx` from Showcase
  - [x] 11.3.b.4 — `pages/Compare.tsx` "Wave 3 — coming soon" empty state with back link
- [x] 11.3.c — Selector dropdowns (Company → Product) + API client wiring to live handlers (`/products`, `/product/:id`, `/mentions?ids=`, `/brief/:id`) *(session 18 — 8 sub-bites; 293 backend tests / mypy / ruff / tsc all green; live curl confirms `latest_brief_id=1` (Alienware), `=2` (ROG); brief headings route via new "strengths"/"weaknesses" keyword set)*
  - [x] 11.3.c.1 — Backend `latest_brief_id` on `ProductDetail` (+ 1 new test, 2 updated)
  - [x] 11.3.c.2 — Frontend type mirror + fixture update
  - [x] 11.3.c.3 — BriefPanel keyword extension (fork 1c — additive, no cache invalidation)
  - [x] 11.3.c.4 — `api.ts` typed route helpers (fork 2 — vanilla fetch, no React Query per YAGNI)
  - [x] 11.3.c.5 — `atoms/Select.tsx` native-select wrapper (fork — §5.6 custom-dropdown deviation flagged)
  - [x] 11.3.c.6 — About: live `/api/products` + two dependent Selects + Open button (fork 4 — plain loading/error treatment)
  - [x] 11.3.c.7 — Standalone: full state-machine swap for product / brief / mentions
  - [x] 11.3.c.8 — Drawer + CitationPanel optimistic-open `loading`/`errorMessage` props
- [x] 11.3.d — End-to-end smoke against `brief_id=1, 2` on `data/pulse_check.db`. Headless-Chromium walk via Playwright (uvicorn-served unified build at :8901) covers: About selectors populate from `/api/products` + filter on company switch + Open-standalone navigates → Standalone (Alienware) loads `latest_brief_id=1`, both polarity buckets route via new "strengths"/"weaknesses" keywords, EvidenceDrawer opens on aspect-row click + `/api/mentions` resolves, CiteChip opens CitationPanel + resolves → Standalone (ROG) `latest_brief_id=2` likewise routes both buckets → `/standalone/garbage` 404 card echoes id → Showcase renders → Compare placeholder renders. Only console "error" was the expected backend 404 on `/api/product/garbage`. **Awaiting operator visual confirm**; screenshots stashed at `C:/Users/AW-testing/AppData/Local/Temp/smoke_11_3_c/`. *(session 18)*

---

## Wave 3 — Aspect 2 (weeks 4–5)

**Goal:** full A2 pair view for all 10 demo pairs; all classifiers pass thresholds.

**Exit criteria:**
- Deliberation classifier ≥ 85% on `deliberation_v1.json`
- Outcome extraction ≥ 85% on `outcome_v1.json`
- Reason tagger ≥ 80% on `reason_tagging_v1.json`
- Intensity tagging ≥ 80% across both tasks
- `/pair/:pair_id` renders WinRateHeader + ReasonRows × 6–8 per side + BriefPanel for all 10 demo pairs
- All briefs citation-validated

### Tasks

**Tagging**
- [ ] Qwen deliberation-thread classifier — `is_deliberation`, `is_resolved`, `products_discussed`, `chosen_product_id`
- [ ] Qwen outcome extractor (if separated from deliberation classification)
- [ ] Qwen reason tagger — `reason_bucket`, `polarity`, `intensity` per comment in a resolved thread
- [ ] Snapshot tests on all three prompts

**Gold sets + eval**
- [ ] Build `deliberation_v1.json`, `outcome_v1.json`, `reason_tagging_v1.json` via Sonnet + spot-check flow
- [ ] Run eval; iterate prompts until all thresholds met

**Aggregation**
- [ ] A2 pair_win_rates aggregator — per pair, count resolved threads by `chosen_product_id`
- [ ] A2 aggregates_pair_reason aggregator — per `(pair, winning_product, reason_bucket)` with provenance
- [ ] Considered-mention corpus — BestBuy/Amazon reviews + YouTube + article mentions cross-referencing pairs, via secondary attribution
- [ ] Unit tests on invariants

**Synthesis**
- [ ] Sonnet addressability classifier per reason bucket (with sample verbatims in context)
- [ ] Sonnet A2 verbatim selection
- [ ] Sonnet A2 brief writer with citation contract
- [ ] Citation validator coverage for A2 briefs

**API**
- [ ] `/pairs` — list pairs in current run
- [ ] `/pair/:id` — win-rate + reason buckets per side + addressability + brief
- [ ] `/threads?pair_id=...` — resolved thread list for drilling win-rate numbers

**Frontend**
- [ ] Page `/pair/:id` — WinRateHeader, two-column ReasonRow tables, BriefPanel
- [ ] `ReasonRow` component with addressability chip
- [ ] `WinRateHeader` component
- [ ] Pair selector (dropdown or segmented control) in page header
- [ ] Landing page tabs — A1 product selector + A2 pair selector

---

## Wave 4 — Eval + polish (weeks 5–6)

**Goal:** all classifiers locked in; UI polished against the design system; edge cases handled.

**Exit criteria:**
- Full eval suite green across all tasks
- DESIGN_SYSTEM §3 tokens implemented; all shadcn components themed
- Empty states, loading skeletons, error states all rendered per design
- Accessibility pass — WCAG AA, keyboard nav verified
- Tombstoning flow tested on a deliberately-deleted fixture mention

### Tasks

- [ ] Eval iteration — revisit any classifier approaching but not exceeding threshold; refine prompts or anchor examples
- [ ] Gold-set refinement — revisit edge cases flagged during spot-check; add difficult cases to the gold set
- [ ] Design-system implementation — full token rollout, font loading, dark-mode root
- [ ] Empty states — "fewer than 100 mentions for this pair" / "no resolved threads found" / "no data yet for this aspect"
- [ ] Loading skeletons — shadcn defaults for initial render
- [ ] Error states — API failure, stale data, malformed response
- [ ] Accessibility — focus rings, keyboard shortcuts, screen-reader labels on every AggregateNumber + citation marker, `prefers-reduced-motion` respected
- [ ] Performance check — evidence drawer pagination for aggregates with > 500 mentions; ensure aggregate queries are indexed
- [ ] Tombstoning — `verify_mentions` job wired; UI badge verified; integration test with a deliberately-tombstoned fixture

---

## Wave 5 — Demo run + hardening (weeks 6–7)

**Goal:** first full pilot run on the 7-product demo set; reproducibility proven; ready for stakeholder review.

**Exit criteria:**
- Real `configs/product_set_gaming_laptops_2026.yaml` with all 7 products, URLs, attribution patterns, YouTube + article seeds
- Full scrape + tag + aggregate + synthesize run completes overnight
- All 7 product scorecards render cleanly; all 10 pair briefs surface at least one actionable finding
- Re-run with same config produces byte-identical aggregates and briefs (cache hits across the board)
- Operator has manually reviewed every brief + verbatim set

### Tasks

- [ ] Populate demo product-set config — real URLs, alias lists, regex patterns per product
- [ ] Load YouTube + article seed lists (curated in parallel prerequisite)
- [ ] Full scrape overnight via Scheduler — verify resumability
- [ ] Full tagging overnight — monitor Qwen throughput
- [ ] Aggregation + synthesis — all pairs + all products
- [ ] Manual review of every output — flag any brief with thin evidence, any aggregate with suspicious counts, any verbatim that seems mis-attributed
- [ ] Bug-fix round based on review findings
- [ ] Reproducibility test — re-run scrape + tag + aggregate; verify cache hits + identical outputs
- [ ] Stakeholder review prep — screenshots, one-page narrative, talking points

---

## Wave 6 — Buffer (week 8)

**Goal:** slippage absorption; optional polish.

Use only if earlier waves ran over. If Waves 1–5 landed on time, this week is spent on:

- [ ] README refresh; SESSION_LOG finalization
- [ ] Anchor attribution regex refinement based on scrape findings
- [ ] Any deferred non-blocking items from the Open Questions list

Or, if desired, start early on v1.5 items:
- [ ] PDF / markdown brief export
- [ ] Rolling-forward scheduler production run
- [ ] Tombstoning retention policy formalization

---

## Dependency summary

```
Wave 1 ─────► Wave 2 ─────► Wave 3 ─────► Wave 4 ─────► Wave 5 ─────► (Wave 6 buffer)
(foundation)   (A1)            (A2)           (eval +       (demo run +
                A1-cutpoint ^                   polish)        hardening)

Parallel prereq: seed-list curation (starts week 0, done by Wave 5)
```

Each wave's tasks are roughly ordered top-to-bottom within the wave; some parallel execution is possible within a wave but cross-wave dependencies are strict. A1 (Wave 2) must precede A2 (Wave 3) because A2 reuses A1's per-mention aspect tags.
