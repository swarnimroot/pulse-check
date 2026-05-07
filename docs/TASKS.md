# pulse-check — Tasks

**Status:** draft &nbsp;·&nbsp; **Paired docs:** [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`TESTING.md`](TESTING.md) &nbsp;·&nbsp; **Last reconciled:** 2026-05-07 (session 9 wrap-up)

Wave-by-wave implementation plan matching the PRD's ~7–8 week single-operator estimate. Each wave has clear outputs, specific tasks, dependencies, and exit criteria. **Wave 2 is the A1-only cutpoint** — if v1 slips, A1 alone is a defensible ship.

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

**Status:** ~75% complete. Tagging + gold-set build + A1 aggregation done on real corpus (session 5). Content-type pre-classifier + tag-time gate (session 6, bite 6.1). Reddit-deepen via comment inheritance (session 8, bite 6.2-revised) — corpus 33 → 1143 mentions; aspect_tags 95 → 649. **Option 3 — A1 aggregate PRIMARY/SECONDARY column split — DONE (session 9, alembic `b8560c93bbd8`).** Aggregate rows 18 → 22; PRIMARY mentions_contributing=71 preserved, SECONDARY mentions_contributing=578 newly visible. Preview brief regenerated with sidebar. Eval runner, full synthesis layer (clusterer / verbatim selector / brief writer / citation validator), A1 API endpoints, and scorecard frontend remain.

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
- [ ] Haiku near-duplicate clusterer (usable for A2 too; build here so A1 can leverage)
- [ ] Sonnet verbatim selector — returns IDs only
- [ ] Sonnet A1 brief writer with citation contract per ARCHITECTURE §6.3
- [ ] Citation validator — rejects fabricated IDs, enforces retry per TESTING §6
- [ ] Integration test — end-to-end brief generation on fixture corpus

**API**
- [ ] `/products` — list products in current run *(stub-only in `api/main.py`; needs population)*
- [ ] `/product/:id` — scorecard data (aspects + aggregates + brief)
- [ ] `/mentions?ids=...` — resolve mention_ids to full cards (used by evidence drawer)
- [ ] `/brief/:id` — single brief with citations

**Frontend**
- [ ] Page `/product/:id` — AspectRow table, BriefPanel, cohort toggles *(Wave 1 shell only)*
- [ ] `VerbatimCard` component with all chips + tombstone badge
- [ ] `AggregateNumber` component with drawer trigger
- [ ] `EvidenceDrawer` with filters (source, verified, recency, intensity)
- [ ] `BriefPanel` — inline citation markers with hover-tooltip + click-to-pin

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
