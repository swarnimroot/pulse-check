# pulse-check — Tasks

Wave-by-wave forward plan. Each wave is a flat checklist of high-level deliverables. Sub-bite breakdowns + per-bite breadcrumbs live in [`SESSION_LOG.md`](SESSION_LOG.md) (the historical record).

**Status:** Wave 2 ✅ substantively complete (aspect-tagging F1=0.7778 on operator-verified N=8; formal ≥80% deferred to Wave 5 rebuild). **Wave 3 in active build** — deliberation + reason classifier modules + Sonnet labelers + gold-set sampler + orchestrator + CLI + operator review CLI all shipped (bites 13.a-13.c.4); eval iteration + A2 aggregators + pair UI still pending. **Wave 5 in active build — Notebookcheck unblocked session 27** via scrapers-lib v1.4.0 (curl_cffi Chrome120 TLS impersonation; root cause was orphan v1.1.0 install + no pyproject pin, NOT User-Agent). **New `catalog_discovery` module + CLI** POST-search Notebookcheck per product `display_name` → editorial reviews filtered by URL slug → per-product YAML for operator curation. Live smoke on ROG Strix G16 returned 18 results → 2 editorial reviews (~1s, $0). RSS title_keywords tightened (drop bare `review`/`best`; add `laptop review`/`best laptop`). Full 59-product discovery + curation + orchestrator integration pending session 28. Waves 4–6 ahead.
**Active:** session 27 audited prior (GREEN: 565 tests / mypy 114 src / ruff) + paired with operator's parallel Claude session that shipped scrapers-lib v1.4.0 (curl_cffi Chrome120 via `warmed_curl_session`; verified end-to-end on the 3 failing session-26 Notebookcheck URLs from this machine). Pinned `scrapers-lib>=1.4.0` in `pyproject.toml` + added `curl_cffi.*` to mypy override. Tightened `configs/wave5_rss_sources.yaml` title_keywords + updated `tests/unit/config/test_loader.py` assertions. Built bite 27.X — `pulse_check/scraping/catalog_discovery.py` (POST search + regex parse + editorial-slug filter + Pydantic `DiscoveredReview` / `DiscoveryResult` for YAML round-trip) + `scripts/discover_notebookcheck.py` CLI (`--product-set` / `--product-id` / `--out-dir` / `--pace` / `--dry-run`) + `tests/unit/scraping/test_catalog_discovery.py` (15 tests against captured HTML fixture at `tests/fixtures/html/notebookcheck_search_rog_strix_g16.html`) + live smoke on ROG Strix G16 → first per-product YAML at `data/discovered_urls/notebookcheck/rog_strix_g16.yaml` (2 editorials, both with full metadata, `approved: false` defaults). **580/580** unit tests green · mypy clean (117 src files; +3 for module + CLI + tests) · ruff clean. **ARCH §6.1 unchanged this session** (no LLM-contract changes).
**Last reconciled:** 2026-05-12 (session 27 — Notebookcheck Cloudflare bypassed via scrapers-lib v1.4.0; catalog_discovery shipped; live smoke validated)

**Waiting on operator action (cross-wave):**
- Operator visual confirm against live uvicorn (Wave 2 frontend smoke completed; ~5-min browser walk; screenshots at `C:/Users/AW-testing/AppData/Local/Temp/smoke_11_3_c/`)
- Install Ollama + pull `qwen2.5:7b-q4_K_M` (Wave 3 prereq)
- `playwright install chromium` (Tier 2/3 source support)
- YouTube channel handle list + review-site RSS feed URLs (~10 channels + ~9 sites — needed at session 25 when rss_discovery bite lands)

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
- [ ] Gold sets: `deliberation_v1` (built N=7 + operator-reviewed) · `reason_tagging_v1` (empty in v1 corpus → Wave 5 rebuild)
- [ ] Deliberation classifier v2: `chosen_external_name` field for "tracked products lost to external winner" signal
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

**Goal:** First full pilot run on the 59-product gaming-laptop competitive set; reproducibility proven; ready for stakeholder review.
**Exit:** Product-set config with all 59 products + regex · staged then full scrape+tag+aggregate+synthesize · all scorecards + Alienware pair briefs render cleanly · re-run produces byte-identical outputs · operator manually reviewed every brief.

- [x] Populate product-set config (59 products: aliases, attribution regex, collision-disambiguated patterns)
- [x] Wave 5 staged run config + staged pair plan (13-product subset, 36 Alienware-anchored pairs)
- [x] RSS-discovery bite (`pulse_check/scraping/rss_discovery.py`) — YouTube channel RSS + review-site RSS → title filter → existing Article + YouTube fetchers; `RSSWindow` added to `SourceWindows`; `RunConfig.rss_sources` field; orchestrator pre-enqueue path (coexists with per-product seeds); HTML auto-discovery fallback for index-page URLs (RTINGS)
- [x] Operator-supplied: YouTube channel handle list + review-site RSS feed URLs (`configs/wave5_rss_sources.yaml`)
- [x] Staged Wave 5 scrape (RSS-only, 13-product subset, 3-month backfill, Reddit untouched) — dry-run visibility CLI shipped (`scripts/dry_run_rss_discovery.py`); YAML tuned from dry-run findings; live scrape ran; YouTube path validated (18 new mentions + 192 secondary attribs); article path produced 0 attributable mentions; Notebookcheck 403 dropped 18 highest-quality admits → triage follow-ups below
- [x] Notebookcheck Cloudflare bypass (scrapers-lib v1.4.0 — `warmed_curl_session` wraps `fetch_article` in curl_cffi Chrome120 TLS impersonation; root cause was orphan v1.1.0 install + no pyproject pin, NOT User-Agent. Pin added.)
- [x] Notebookcheck `catalog_discovery` module + CLI (`pulse_check/scraping/catalog_discovery.py` + `scripts/discover_notebookcheck.py`; POST search by `display_name` → URL-slug filter to editorial reviews → per-product YAML at `data/discovered_urls/notebookcheck/<product_id>.yaml` for operator curation. Live smoke on ROG Strix G16: 18 results → 2 editorials.)
- [x] RSS title_keywords tightening (drop bare `review`/`best`; add `laptop review`/`best laptop`) — kept as supplementary discovery path; catalog_discovery is primary
- [ ] Full 59-product Notebookcheck catalog discovery run (`scripts/discover_notebookcheck.py --product-set configs/product_set_gaming_laptops_2026.yaml`) — ~3-4 min wall-clock, $0
- [ ] Operator curation pass (flip `approved: true` on legitimate matches per product YAML; delete spurious)
- [ ] Orchestrator integration of approved discovered URLs (read per-product YAMLs → enqueue against existing `fetch_article` path — now Cloudflare-bypassing via v1.4.0)
- [ ] (Optional) JS-rendered external-URL Playwright path — Notebookcheck spec/aggregation pages embed external review URLs (Tom's Hardware / PCMag / etc.) via JavaScript; spike could 5-10x corpus
- [ ] Article RSS-path strategy decision — superseded by catalog_discovery as primary path; broad RSS feeds kept as opportunistic supplement (no further action gating Wave 5)
- [ ] Full Wave 5 scrape on all 59 products (reverse session-26 staged flips: reddit `enabled: true`, rss `backfill_months: 6`)
- [ ] Full aspect/deliberation/reason tagging overnight
- [ ] Deliberation classifier v2: `chosen_external_name` field for "tracked products lost to external winner" signal (Wave 3 carry-over, bundled before gold rebuild)
- [ ] Aspect-tagging gold-set rebuild on filtered corpus at target N=150 (carries Wave 2 formal ≥80% closure)
- [ ] Deliberation + reason gold-set rebuild on expanded corpus (Wave 3 carry-over: v1 corpus had zero resolved-to-tracked-product threads)
- [ ] Aggregation + synthesis for all pairs + all products
- [ ] Manual review of every brief + aggregate + verbatim attribution
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
- [x] YouTube channel handle list (7 channels, resolved + channel IDs verified) and review-site RSS feed URLs (9 sites, 3 GREEN / 5 YELLOW / 1 RED) supplied at session-24 close — see `configs/wave5_rss_sources_draft.yaml`
