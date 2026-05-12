# pulse-check — Tasks

Wave-by-wave forward plan. Each wave is a flat checklist of high-level deliverables. Sub-bite breakdowns + per-bite breadcrumbs live in [`SESSION_LOG.md`](SESSION_LOG.md) (the historical record).

**Status:** Wave 2 ✅ substantively complete (aspect-tagging F1=0.7778 on operator-verified N=8; formal ≥80% deferred to Wave 5 rebuild). Waves 3–6 ahead.
**Active:** session 22 audited prior + shipped bite 13.c.1 — two Sonnet labeler modules (`pulse_check/eval/deliberation_labeler.py` + `pulse_check/eval/reason_labeler.py`) reusing production `build_prompt` + `parse_response` from `deliberation_classifier` / `reason_tagger` verbatim; cache namespace separated via `task="*_labeling"` + dedicated `*_labeling_v1` `PROMPT_VERSION`s; `_DEFAULT_MODEL="claude-sonnet-4-6"`; 40 MagicMock-based unit tests (20 per labeler); mypy + ruff clean; **469/469** full suite green. Live Sonnet labeling deferred to 13.c.3 per locked sub-bite split. **ARCH §6.1 unchanged this session** — labelers literally use the existing classifier/tagger prompts. Pending operator review of 13.c.1; next is 13.c.2 (sampler — stratified Reddit thread/comment selection with force-included edge cases) — settle five pre-bite shape decisions before code.
**Last reconciled:** 2026-05-12 (session 22 — bite 13.c.1 shipped)

**Waiting on operator action (cross-wave):**
- Operator visual confirm against live uvicorn (Wave 2 frontend smoke completed; ~5-min browser walk; screenshots at `C:/Users/AW-testing/AppData/Local/Temp/smoke_11_3_c/`)
- Install Ollama + pull `qwen2.5:7b-q4_K_M` (Wave 3 prereq)
- `playwright install chromium` (Tier 2/3 source support)
- Curate YouTube + article seed lists (Wave 5 prereq; ~50–75 YT URLs + ~150–200 article URLs)

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
- [x] Aspect-tagging eval runner (`scripts/run_eval.py`; F1=0.7778 operator-verified on filtered N=8)
- [ ] Operator visual confirm against live uvicorn *(operator-side, ~5 min)*
- [ ] BestBuy + Amazon retailer-reviews path *(deferred — 3 plumbing items)*
- [ ] Iterate aspect classifier prompt *(deferred unless Wave 5 rebuild still misses 80%)*
- [ ] Full brief-generation integration test on fixture corpus *(deferred to Wave 4)*

---

## Wave 3 — Aspect 2 (A2 — comparative pairs)

**Goal:** Full A2 pair view for all 10 demo pairs; deliberation + outcome + reason classifiers pass thresholds.
**Exit:** Deliberation ≥85% · outcome ≥85% · reason ≥80% · intensity ≥80% · `/pair/:id` renders WinRateHeader + ReasonRows + BriefPanel for all 10 pairs · all briefs citation-validated.

- [ ] Deliberation thread classifier (Qwen): `is_deliberation`, `is_resolved`, `products_discussed`, `chosen_product_id`
- [ ] Reason tagger (Qwen): `reason_bucket` + polarity + intensity per comment in resolved threads
- [ ] Snapshot tests on classifier prompts
- [ ] Gold sets: `deliberation_v1`, `reason_tagging_v1` (Sonnet-labeled on content-type-filtered corpus)
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
- [ ] Empty states ("fewer than 100 mentions", "no resolved threads", "no data yet")
- [ ] Loading skeletons (shadcn defaults)
- [ ] Error states (API failure, stale data, malformed response)
- [ ] Accessibility (focus rings, keyboard nav, screen-reader labels, `prefers-reduced-motion`)
- [ ] Performance (drawer pagination >500 mentions, aggregate query indexes)
- [ ] Tombstoning (`verify_mentions` job wired + UI badge + fixture integration test)
- [ ] Full brief-generation integration test on fixture corpus (carries the Wave 2 deferral)

---

## Wave 5 — Demo run + hardening

**Goal:** First full pilot run on 7-product gaming-laptop demo set; reproducibility proven; ready for stakeholder review.
**Exit:** Real product-set config with all 7 products + URLs + regex · full scrape+tag+aggregate+synthesize overnight · all 7 scorecards + 10 pair briefs render cleanly · re-run produces byte-identical outputs · operator manually reviewed every brief.

- [ ] Populate demo product-set config (7 products: URLs, alias lists, attribution regex)
- [ ] Load operator-curated YouTube + article seed lists
- [ ] Full scrape overnight via Scheduler (verify resumability)
- [ ] Full aspect/deliberation/reason tagging overnight
- [ ] Aggregation + synthesis for all pairs + all products
- [ ] Manual review of every brief + aggregate + verbatim attribution
- [ ] Aspect-tagging gold-set rebuild on filtered corpus at target N=150 (carries Wave 2 formal ≥80% closure)
- [ ] Bug-fix round from review findings
- [ ] Reproducibility test (re-run, verify cache hits + byte-identical outputs)
- [ ] Stakeholder review prep (screenshots, narrative, talking points)

---

## Wave 6 — Buffer

**Goal:** Slippage absorption; optional polish if Waves 1–5 land on time.

- [ ] README refresh + SESSION_LOG finalization
- [ ] Attribution regex refinement from scrape findings
- [ ] Deferred non-blocking items from Open Questions
- [ ] (Optional v1.5) PDF/markdown brief export, rolling-forward scheduler, tombstoning retention policy

---

## Parallel operator-side prerequisite

Operator-side setup running alongside code work; not blocking Wave 1 start.

- [x] Python 3.12 + `.venv`
- [x] Anthropic API key in `.env`
- [x] scrapers-lib editable install from sibling directory
- [ ] Install Ollama + pull `qwen2.5:7b-q4_K_M` *(Wave 3 prereq)*
- [ ] `playwright install chromium` *(for Tier 2/3 sources)*
- [ ] Curate YouTube seed list (~50–75 URLs total for 10-pair demo)
- [ ] Curate article seed list (~150–200 URLs)
