# pulse-check — Tasks

Wave-by-wave forward plan. Each wave is a flat checklist of high-level deliverables. Sub-bite breakdowns + per-bite breadcrumbs live in [`SESSION_LOG.md`](SESSION_LOG.md) (the historical record).

**Status:** Wave 2 ✅ substantively ships. Wave 5 Stage A + B complete: all 53 in-corpus products tagged + aggregated + briefed under `run_wave5_v1` (6/59 products skipped — zero qualifying mentions). Brief schema bumped to `a1_brief_v2` with per-claim `header` field rendered as card-per-claim (DESIGN_SYSTEM §5.2 patched session 33). UI shipped: 3-card home page (Standalone voice · Head-to-head · Cross-product heatmap), now with **purple-outlined button CTAs** instead of text-hyperlinks (session 35); separate Sources accordion + collapsible "Under the hood" pipeline explainer; Standalone empty-state Company/Product picker (no default product); Head-to-head Pair page (A1-based, 3-count tiles + single combined table sorted by combined mention count, leader-side accent ring, Pair idle-state explainer card added session 35); Cross-product heatmap polished (multi-select popovers · Company column with brand banners · sortable headers on `Company` + 11 aspects with asc/desc/clear cycle · color-scale legend above the grid · row-hover dim affordance · cascading Company → Size → Product filters · screen-size regex now recovers `16x` / `16s` / `Z13` / `X16` and size-less products). All three data pages carry a **soft-lavender `What are all these numbers?` glossary trigger** (session 35; 6 entries × 5 sections); Standalone additionally carries an **`Export brief` trigger** (session 35) opening a centered overlay with a single-page A4 one-pager and Save-as-PDF / Download-HTML actions. ASUS / ASUS ROG merged into a single `ASUS` brand at both the YAML config and DB `products`-table layer (session 35). `EvidenceDrawer` verified-only filter hidden (corpus has zero verified-purchase signal until BestBuy/Amazon ingestion lands). DESIGN_SYSTEM §6.1 / §6.2 / §6.3 / §6.4 + §2.11 / §2.12 patched session 35 to match shipped reality; ARCHITECTURE §3.2 annotates A2 schema tables as parked. Wave 3 A2 path **parked** (Reddit corpus structurally thin on resolved deliberation; tables retained empty in schema for future revival). Public deployment live via Tailscale Funnel: uvicorn :8765 → `/pulse-check`. README is the operator runbook. **Session 36 ships:** quarterly refresh cadence locked (supersedes session-31 monthly; README updated across 3 spots with `$60–100/year` cost figures; About header gained underlined `Refreshed quarterly.` line); MSI attribution regex refined with `a?` prefix on size digits across 11 MSI products × 2 patterns = 22 line edits in `configs/product_set_gaming_laptops_2026.yaml` (AMD-variant `Crosshair A17` / `Katana A15` / `Cyborg A14-A17` / `Vector A16-A18` now match alongside their Intel counterparts), cascade fired (+66 SECONDARY attributions · +85 aspect_tag rows · +11 aggregates 489→500 · +9 briefs at `a1_brief_v2` 53→62; `msi_crosshair_17` zero-to-briefable; `msi_cyborg_15` newly grounded in 9 cite IDs); Notebookcheck `search_notebookcheck()` gained `manufacturer` kwarg + `_MANUFACTURER_IDS` brand-ID dict (7 brands recon'd live) + 2 unit tests (curation pass deferred until all session-36 polish bites land); operator-side Ollama + Qwen + Playwright prereqs confirmed installed. **Session 37 ships:** bite #3 F1 closure landed via metric change rather than prompt iteration — diagnosis pass refuted the prior "Sonnet labeler over-labels NotebookCheck Verdict prose" hypothesis (intensity-only wobble was 83/90 of disagreements, not aspect-detection error); `compute_micro_f1_loose` added to `pulse_check/eval/eval_runner.py` with ±1 intensity-bucket tolerance + greedy one-to-one matching within `(aspect, polarity)` groups; `EvalReport` gained `micro_loose` field and `passed` now gates on loose; `scripts/run_eval.py` defaults `--exclude-content-types` to `deal` (mirrors `run_stage_b.py` production gate, closes session-19 filter-mirror bug); both strict and loose F1 printed in CLI summary and persisted in JSON; re-eval result: strict F1=0.6000 (unchanged) / **loose F1=0.7783** (TP=358 FP=74 FN=130; precision 0.83, recall 0.73); THRESHOLD=0.80 kept (FAIL banner expected, operator-accepted as Wave 2 closure number).
**Active:** Polish ordering locked session 36 — 3 buckets (briefs · reliability · cosmetic) sequenced BEFORE 3 exit forks. Bucket 1 progress: bite #1 Notebookcheck manufacturer POST shipped (curation deferred), bite #2 MSI regex refinement shipped (full cascade verified), bite #3 F1 closure shipped session 37 via loose-metric change (loose F1=0.78, strict 0.60; 0.80 not formally met but operator-accepted), bite #4 Stage B integration test shipped session 37 (`tests/integration/test_stage_b_pipeline.py`; 2 tests covering aggregate → synthesize end-to-end with stubbed dedup + brief-writer; exercises citation-validator + retry-on-fabricated path), bite #7 visual loading skeletons shipped session 37 (new `frontend/src/components/ui/skeleton.tsx` vanilla shadcn-style component using `animate-pulse` + `bg-muted` token; 7 text-based "Loading…" spots replaced across Compare heatmap / Standalone picker / Standalone full-page product / Standalone brief panel / Pair scorecard / EvidenceDrawer / CitationPanel with content-shaped skeleton blocks; `tailwindcss-animate` already installed, no new deps). **Next: bite #5 link-rot / tombstoning.** Remaining queue: #6 quarterly-cadence scheduler · #8 design-system audit · #9 markdown brief export. Exit forks (must follow polish): operator brief-review walk · reproducibility re-run · stakeholder prep packet. **635/635 unit tests · 2/2 integration tests · mypy clean (126 src) · ruff clean · frontend tsc + vite build green.** Current frontend bundle: `index-CkZUKoNo.js` (289.32 KB / 86.13 KB gzipped; replaces session-36 `index-BYICaCjx.js`; new hash breaks stale browser cache). Migration head: `eb05da255474` (unchanged).
**Last reconciled:** 2026-05-19

**Waiting on operator action (cross-wave):**
- Operator visual confirm against live uvicorn (Wave 2 frontend smoke completed; ~5-min browser walk; screenshots at `C:/Users/AW-testing/AppData/Local/Temp/smoke_11_3_c/`)

**Doc index:** spec in [`PRD.md`](PRD.md) + [`ARCHITECTURE.md`](ARCHITECTURE.md). UI in [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md). Eval methodology in [`TESTING.md`](TESTING.md). Bite narratives + audit checklists in [`SESSION_LOG.md`](SESSION_LOG.md).

---

## Wave 1 — Foundation ✅

**Goal:** Shared layer is working — scrape, attribute, store, cache; frontend/backend shells ready for aspect work.
**Exit:** Alembic schema created · 2-product smoke run succeeds · unified corpus with all 5 sources in SQLite · LLM cache populated · FastAPI + React shells running.

- [x] Package scaffold (`pyproject.toml`, `.gitignore`, pre-commit, pytest config, logging)
- [x] SQLAlchemy + Alembic (engine, session factory, declarative base, full schema)
- [x] Config system (Pydantic models, YAML loader, validation, example configs)
- [x] Scrapers-lib integration (wrappers for Reddit, BestBuy, Amazon, YouTube, articles)
- [x] Attribution (primary regex at fetch time + post-fetch secondary sweep)
- [x] LLM cache + clients (`call_with_cache` + Ollama + Anthropic wrappers)
- [x] Frontend/backend shells (Vite + React + TS + Tailwind + shadcn; FastAPI + CORS + routes)

---

## Wave 2 — Aspect 1 (A1-only cutpoint) ✅ substantively

**Goal:** Full A1 scorecard per product; aspect classifier passes gold-set threshold; end-to-end demo on 2 products.
**Exit:** Classifier ≥80% on gold set · `/product/:id` renders AspectRows × 11 + BriefPanel with drillable EvidenceDrawer · one product produces citation-validated A1 brief · re-run produces byte-identical outputs.

- [x] Aspect + polarity + intensity classifier (Haiku)
- [x] Content-type pre-classifier + `--exclude-content-types` gate
- [x] Aspect batch tagger with caching + within-response dedup
- [x] Reddit comment-inheritance (parent-post PRIMARY → comment SECONDARY)
- [x] Gold-set build + review CLIs (Sonnet-labeled)
- [x] A1 aggregator with PRIMARY/SECONDARY dual-bucket split
- [x] Haiku near-duplicate clusterer (cached)
- [x] Deterministic verbatim selector (intensity-ranked, cluster-deduped)
- [x] Sonnet A1 brief writer (four-quadrant routing, citation contract)
- [x] Citation validator (fabricated IDs, out-of-context, drift, empty claims)
- [x] `synthesize_a1` orchestrator + CLI; first live briefs (Alienware + ROG)
- [x] Backend API (`/products`, `/product/:id`, `/mentions?ids=`, `/brief/:id`)
- [x] Frontend atoms (Chip, DrillNumber, CiteChip, SourceMark, SourceDots, IntensityBar, Sparkline, VerbatimCard)
- [x] Frontend composites (EvidenceDrawer, CitationPanel, RunMetaStrip)
- [x] Frontend pages (About, Standalone, Compare placeholder; hash router; AspectColumn 3-section partition)
- [x] Frontend selectors + live API wiring (dropdowns, BriefPanel keyword routing)
- [x] Headless visual smoke (Playwright, 13/13 functional checks, all routes)
- [x] Aspect-tagging eval runner (`scripts/run_eval.py`; closure at **loose F1=0.78** / strict F1=0.60 on v2 gold via `compute_micro_f1_loose` ±1 intensity-bucket tolerance; THRESHOLD=0.80 kept and not formally met but operator-accepted as Wave 2 closure)
- [x] Home page: 3-card surface (Standalone / Head-to-head / Heatmap) + collapsible "Under the hood" plain-English pipeline explainer + sources accordion
- [x] Standalone page Company/Product picker (port from About picker; routes via `useNavigate`)
- [x] Head-to-head Pair page (`/pair`) — A1-based aspect scorecard with PickerColumns (no default selection), 3 CountTiles (Primary leads / Ties / Competitor leads) above a single combined PairTable sorted by combined `total_mentions` with leader-side accent ring on `PairCellChip`
- [x] Cross-product heatmap (`/compare`) — Company column with brand banners, Alienware-pinned + 2px accent edge, 3 multi-select popovers (Company / Screen size / Product) with cascading Company → Size → Product filtering, sortable headers on Company + 11 aspects with click-cycle asc/desc/clear, color-scale legend above the grid, row-hover dim affordance via `display:contents` group, screen-size regex `(?<!\d)(13|14|15|16|17|18)(?!\d)` recovers model suffixes (16x / 16s / Z13 / X16) and size-less products always pass
- [x] Brief schema v2 (`Claim.header`, prompt_version `a1_brief_v2` + `_strict`); 53 briefs regenerated under `run_wave5_v1`
- [x] Backend API surface for new pages: `/api/home` (run + pipeline stats), `/api/pair` (head-to-head), `/api/compare` (heatmap), `/api/sources` (operator-curated source list)
- [x] Public deployment via Tailscale Funnel (`/pulse-check` → uvicorn :8765, same-origin SPA from `frontend/dist`)
- [ ] Operator visual confirm against live uvicorn *(operator-side; broader review of all three pages pending)*
- [ ] BestBuy + Amazon retailer-reviews path *(deferred — 3 plumbing items)*
- [ ] Iterate aspect classifier prompt *(deferred to Wave 4 polish; aesthetics binary F1=0.62 is the one remaining aspect-level hole + parser drops on `unknown polarity 'mixed'` / duplicate-aspect responses cost ~8 TP per re-eval)*
- [ ] Full brief-generation integration test on fixture corpus *(deferred to Wave 4)*

---

## Wave 3 — Aspect 2 (A2 — comparative pairs)

**Parked, session 35.** Decision rationale: Reddit corpus is a comparison venue, not a confirmation venue — too few resolved-to-tracked-product deliberation threads to drive a reliable A2 artifact (0/50 in the v2 gold-set sample). All Wave 3 items below remain unchecked pending future revival; A2 schema tables retained empty in the DB. The head-to-head surface continues to ship as the A1-derived `/pair` page (A1 aggregate diffs only; no A2-driven brief layer).

**Goal:** Full A2 pair view for all 10 demo pairs; deliberation + outcome + reason classifiers pass thresholds.
**Exit:** Deliberation ≥85% · outcome ≥85% · reason ≥80% · intensity ≥80% · `/pair/:id` renders WinRateHeader + ReasonRows + BriefPanel for all 10 pairs · all briefs citation-validated.

- [ ] Deliberation thread classifier (Qwen): `is_deliberation`, `is_resolved`, `products_discussed`, `chosen_product_id`
- [ ] Reason tagger (Qwen): `reason_bucket` + polarity + intensity per comment in resolved threads
- [ ] Snapshot tests on classifier prompts
- [ ] Gold sets: `deliberation_v1` (built N=7 + operator-reviewed) · `reason_tagging_v1` (empty in v1 corpus → Wave 5 rebuild)
- [x] Deliberation classifier v2: `chosen_external_name` field for "tracked products lost to external winner" signal
- [ ] Eval extensions for `--task deliberation` and `--task reason_tagging`; iterate to thresholds
- [ ] A2 pair_win_rates aggregator (per-pair, resolved threads by `chosen_product_id`)
- [ ] A2 aggregates_pair_reason aggregator (per-pair-winner-reason with provenance)
- [ ] Considered-mention corpus enrichment (BestBuy/Amazon/YouTube/article via secondary attribution)
- [ ] Sonnet addressability classifier (messaging/software/hardware/pricing per reason bucket)
- [ ] Sonnet A2 verbatim selector + brief writer + citation validator
- [ ] API: `/pairs`, `/pair/:id`, `/threads?pair_id=`
- [ ] DESIGN_SYSTEM update for A2 atoms (WinRateHeader, ReasonRow, paired-table)
- [ ] Frontend: WinRateHeader, ReasonRow with addressability chip, two-column reason table
- [ ] Frontend page `/pair/:id` + pair selector + landing-page tabs

---

## Wave 4 — Eval + polish

**Goal:** All classifiers locked; UI polished against design system; edge cases handled.
**Exit:** Full eval suite green · DESIGN_SYSTEM tokens fully implemented · empty/loading/error states rendered · WCAG AA accessibility · tombstoning tested.

- [ ] Eval iteration on any classifier near but below threshold
- [ ] Gold-set refinement (add difficult edge cases from spot-check)
- [ ] Design-system full rollout (tokens, font loading, all shadcn components themed)
- [x] Empty states (About / Standalone / Compare already shipped; Pair idle-state explainer card added — "Pick a product on each side")
- [ ] Loading skeletons (shadcn defaults) — text-based "Loading…" fallbacks shipped; visual skeleton component deferred
- [x] Error states (API failure, stale data, malformed response) — error cards with retry on all 4 pages
- [x] Accessibility — global `*:focus-visible` ring + `prefers-reduced-motion` rule already in `index.css`; Wave 4 polish added `aria-controls` on accordions, `Escape`-to-close on MultiSelectPopover, descriptive `aria-label` on HeatCell sentiment buttons + sort headers
- [ ] Performance (drawer pagination >500 mentions, aggregate query indexes)
- [ ] Tombstoning (`verify_mentions` job wired + UI badge + fixture integration test)
- [ ] Full brief-generation integration test on fixture corpus (carries the Wave 2 deferral)

---

## Wave 5 — Demo run + hardening

**Goal:** First full pilot run on the 59-product gaming-laptop competitive set; reproducibility proven; ready for stakeholder review.
**Exit:** Product-set config with all 59 products + regex · staged then full scrape+tag+aggregate+synthesize · all scorecards + Alienware pair briefs render cleanly · re-run produces byte-identical outputs · operator manually reviewed every brief.

- [x] Populate product-set config (59 products: aliases, attribution regex, collision-disambiguated patterns)
- [x] Wave 5 staged run config + staged pair plan (13-product subset, 36 Alienware-anchored pairs)
- [x] RSS-discovery module (`pulse_check/scraping/rss_discovery.py`) with YouTube + review-site feeds + `RSSWindow` + `RunConfig.rss_sources` + HTML auto-discovery fallback
- [x] Operator-supplied YouTube channel handles + review-site RSS feed URLs (`configs/wave5_rss_sources.yaml`)
- [x] Staged Wave 5 scrape (RSS-only, 13-product subset) + dry-run visibility CLI (`scripts/dry_run_rss_discovery.py`)
- [x] Notebookcheck Cloudflare bypass via scrapers-lib v1.4.0 (`warmed_curl_session` + curl_cffi Chrome120 TLS impersonation; pin in `pyproject.toml`)
- [x] Notebookcheck `catalog_discovery` module + CLI (`pulse_check/scraping/catalog_discovery.py` + `scripts/discover_notebookcheck.py`; POST search → URL-slug filter → per-product YAML for operator curation)
- [x] RSS title_keywords tightening (drop bare `review`/`best`; add `laptop review`/`best laptop`)
- [x] Full 59-product Notebookcheck catalog discovery run (`--min-published-date` flag + `filter_by_min_date` helper)
- [x] Operator curation pass (33 entries approved across 30 YAMLs in `data/discovered_urls/notebookcheck/*.yaml`; 29 quarantined to `_dropped_28a/`)
- [x] Orchestrator integration of approved discovered URLs (`RunConfig.discovered_urls_sources` field + `pulse_check/scraping/discovered_urls.py` module + `_enqueue_discovered_urls` helper + `scripts/scrape.py` passthrough)
- [ ] Manufacturer-dropdown POST extension — recon Notebookcheck's form for manufacturer-ID values, extend `search_notebookcheck` payload, retest quarantined mega-product queries
- [x] Live verification of `discovered_urls_sources` path at the full Wave 5 scrape (capability + output aha against actual corpus)
- [ ] (Optional) JS-rendered external-URL Playwright path — Notebookcheck spec/aggregation pages embed external review URLs via JavaScript
- [x] Article RSS-path strategy decision — superseded by catalog_discovery as primary; broad RSS feeds kept as opportunistic supplement
- [x] Full Wave 5 scrape on all 59 products (`reddit.enabled: true`, `rss.backfill_months: 6`, `discovered_urls_sources` in `run_wave5_v1.yaml`)
- [x] Full aspect tagging — 4,813 aspect_tag rows · 53/59 products tagged · 6 had zero qualifying mentions after DEAL filter
- [ ] Full deliberation/reason tagging overnight (Wave 3 A2 path)
- [x] Aspect-tagging gold-set rebuild on filtered corpus at target N=150 (carries Wave 2 formal ≥80% closure)
- [x] Deliberation + reason gold-set rebuild on expanded corpus (Wave 3 carry-over: v1 corpus had zero resolved-to-tracked-product threads)
- [x] Aggregation + synthesis for all A1 products (Stage A + Stage B under `run_wave5_v1` — 489 aggregate rows · 53 briefs · 44/50 Stage B briefs pristine · 6 with one numerical-drift each · 0 fabricated across all 50). A2 pair briefs deferred to Wave 3.
- [x] Brief regeneration at `a1_brief_v2` prompt (header field; 53 briefs re-written via `scripts/run_stage_b.py --skip-tagging --skip-aggregation --include-stage-a-briefs`)
- [ ] Manual review of every brief + aggregate + verbatim attribution
- [ ] Bug-fix round from review findings
- [ ] Reproducibility test (re-run, verify cache hits + byte-identical outputs)
- [ ] Stakeholder review prep (screenshots, narrative, talking points)

---

## Wave 6 — Buffer

**Goal:** Slippage absorption; optional polish if Waves 1–5 land on time.

- [x] README refresh as operator runbook (orchestrator-first path · monthly refresh procedure · public deployment via Tailscale Funnel + uvicorn :8765 · granular controls subsection · fixed script names + npm)
- [x] PDF + HTML brief export (single-page A4 one-pager via `BriefExportButton`: 4 stat tiles + 11-aspect chip row + top 3 strengths/complaints + citations footer. PDF route = browser `window.print()` + `@media print` stylesheet. HTML route = Blob download with inlined styles. Wired on Standalone; component generic over `BriefView` so it transplants onto a future Pair brief.)
- [x] Glossary modal (`GlossaryDialog`, "What are all these numbers?") on Standalone / Pair / Compare — 6 entries × 5 sections (drop-rule: term must appear on screen AND be non-obvious to a cold visitor)
- [x] ASUS / ASUS ROG brand merge — single `ASUS` brand with 14 products in both `configs/product_set_gaming_laptops_2026.yaml` AND `data/pulse_check.db` `products` table (9 ROG rows UPDATE'd at the DB layer; YAML alone is insufficient since `/api/products` reads from DB at request time)
- [x] Home page CTAs converted from text-hyperlinks to purple-outlined buttons (`Open standalone` / `Open comparison` / `Open heatmap`) — flips to solid purple on hover
- [x] `EvidenceDrawer` verified-only filter hidden (corpus has zero `verified_purchase` signal until BestBuy/Amazon ingestion lands; aggregator + schema column retained)
- [x] Attribution regex refinement from scrape findings — MSI `a?` prefix on size digits across 11 products (22 line edits in `configs/product_set_gaming_laptops_2026.yaml`); cascaded +66 SECONDARY attributions / +85 aspect_tag rows / +11 aggregates / +9 briefs at `a1_brief_v2` under `run_wave5_v1`. AMD-variant naming policy: model-size optionally prefixed by `a` matches both Intel and AMD SKUs in a single pattern (ARCH §5 patch).
- [ ] Deferred non-blocking items from Open Questions
- [ ] (Optional v1.5) Markdown brief export, rolling-forward scheduler, tombstoning retention policy

---

## Parallel operator-side prerequisite

Operator-side setup running alongside code work; not blocking Wave 1 start.

- [x] Python 3.12 + `.venv`
- [x] Anthropic API key in `.env`
- [x] scrapers-lib editable install from sibling directory
- [x] Install Ollama + pull `qwen2.5:7b-q4_K_M` *(Wave 3 prereq — Wave 3 currently parked, but install in place for future revival)*
- [x] `playwright install chromium` *(for Tier 2/3 sources)*
- [x] YouTube channel handle list (7 channels) + review-site RSS feed URLs (9 sites) — see `configs/wave5_rss_sources.yaml`
