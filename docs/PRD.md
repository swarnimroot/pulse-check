# pulse-check — Product Requirements

**Status:** draft &nbsp;·&nbsp; **v1 target:** 2026-Q2 &nbsp;·&nbsp; **Owner:** single operator (initial)

---

## 1. Executive summary

pulse-check is a product-listening pilot engine for PC manufacturers. It takes a configured set of products, pulls public commentary about each one from multiple sources (Reddit, retailer reviews, YouTube, gaming press), and produces a webapp with two focused views:

- **Standalone voice** — per-product aspect scorecard showing what buyers and reviewers consistently praise or complain about.
- **Comparative deliberation** — per-pair decoder showing why public deliberators choose one product over the other, classified by whether the reason is messaging-, software-, hardware-, or pricing-addressable.

The engine is **product-agnostic**: Alienware gaming laptops are the first demo, but the same engine runs any product set through the same analysis. Output is designed for an executive/PM audience — **actionable clarity over data density**.

## 2. Problem statement

A PC manufacturer's internal data (sales, RMA, support tickets, NPS) tells it who bought from it and what broke after they bought. It cannot tell it:

1. **Why prospective buyers chose a competitor instead.** Deliberation happens in public — Reddit threads, retailer review comparisons, YouTube head-to-heads, gaming-press roundups — but is scattered across sources and not anchored to specific SKUs with verified context.
2. **How public perception of a specific SKU compares, aspect-by-aspect, to competitors.** Off-the-shelf social-listening tools produce brand-level sentiment that doesn't distinguish between SKU variants, doesn't cohort reviews by verified-purchase or ownership duration, and undersamples gaming-hardware communities.

pulse-check closes both gaps by pairing the `scrapers-lib` library (for patient, attributed public-data collection) with a local LLM classifier (Qwen 7B via Ollama) for volume work, and Anthropic Sonnet for synthesis and final briefs.

## 3. Target users and audiences

| Audience | Role | What they read |
|---|---|---|
| **Exec / Product Management** *(primary)* | Acts on findings | A1 scorecard + A2 pair-brief contrast paragraph (session 42 shipped — single-paragraph per pair); full A2 (reason buckets + addressability classification telling them *what kind of fix* each reason implies) parked pending corpus deliberation density |
| **Marketing / PR** *(secondary)* | Messaging, positioning, competitive response | A2 pair-brief contrast + verbatim evidence; full reason-bucket detail parked alongside the full A2 pipeline |
| **Operator** *(developer)* | Runs pipelines, reviews outputs, refines taxonomy | Everything; also sees raw mention drill-downs |

Audience bias: **exec-clarity over analyst-depth.** Default views should surface conclusions; detail is one click away.

## 4. Scope

### 4.1 In scope for v1

- **Product-agnostic pilot engine** — accepts a runtime config (product set + pair plan + source windows) and runs the full pipeline end-to-end.
- **Two analysis aspects** in one webapp — Aspect 1 (standalone) and Aspect 2 (comparative deliberation).
- **Five source types** — Reddit sweep + thread fetch; BestBuy paginated reviews; Amazon PDP reviews; YouTube transcripts (hand-seeded URLs); gaming-news articles (hand-seeded URLs).
- **11-aspect taxonomy (v0)** — thermals, performance, keyboard, display, battery, build quality, software experience, price-value, support/warranty, aesthetics, portability. Every mention-aspect tag carries two dimensions: **polarity** (negative / neutral / positive) and **intensity** (low / medium / high).
- **6-month initial backfill** per source; architecture supports per-source windows and rolling-forward extension.
- **Desktop webapp** — dark-mode-first, Alienware aesthetic; product selector + pair selector; verbatim drill-down; per-aspect scorecard; per-pair win-rate + ranked reasons + addressability; no mobile, no multi-user auth.
- **LLM evaluation harness** — Sonnet-built gold sets + operator spot-check + regression tests on classifier accuracy per prompt version.
- **Cloud-migration-ready storage** — SQLAlchemy ORM + Alembic migrations so SQLite→Postgres is a connection-string change.
- **First demo run** on 7 gaming laptops (see §9).

### 4.2 Non-goals (v1)

- **Not a consumer-facing tool.** Output is for manufacturer decision-making, not buyer decision support.
- **Not real-time monitoring.** v1 runs analyses on demand from a stored corpus; rolling-forward is supported architecturally but not a day-1 feature.
- **Not a general brand-sentiment tool.** Every analysis is anchored to a specific product set the operator configures.
- **No automated publishing / alerting.** No emails, Slack, auto-posts.
- **No PDF / markdown export.** Webapp only.
- **No mobile or responsive layouts.** Desktop only.
- **No multi-user auth.** Single operator v1; the optional reverse-proxy share path (§4.3) is read-only and intended for trusted-team viewing, not multi-tenant access control.
- **No competitor-vs-competitor pairs.** v1 pair plan is primary-vs-each-comparator only.
- **No non-English content.** English-language sources only.
- **No automated segment discovery.** A separate future project will maintain the catalog of segment-matched SKUs; pulse-check consumes its output.
- **No LLM at UI time.** All LLM-generated content is precomputed at batch time and cached.

### 4.3 Sharing mode (optional)

The default deployment is single-operator on the operator's machine. A secondary "sharing mode" exists for showing work-in-progress to trusted teammates without a company-network deployment:

- **Unified server.** One FastAPI process serves both API (`/api/*`) and the built SPA on a single port (default 8765). Run via `python scripts/serve_public.py`.
- **Prefix-agnostic.** SPA uses relative asset URLs + `HashRouter`; backend serves API at `/api/*`. The reverse proxy may mount the app at any path (e.g. `/pulse-check`) without code changes.
- **Reverse proxy responsibility.** Auth (if any), TLS termination, and the public hostname are owned by the proxy layer (Tailscale Funnel + a gating home page in current setup). The pulse-check process itself is unauthenticated and trusts the proxy.
- **Read-only.** Every API route is GET-only; there is no write surface. Once the smoke scrape lands, real Reddit text and synthesized briefs become readable to anyone the proxy admits — the proxy gate is the only access control.

When the share path is in use, the data-visibility footprint expands beyond the operator's machine; the proxy gate (e.g. password-protected home page) is the boundary.

## 5. The two aspects

### 5.1 Aspect 1 — Standalone product voice

**Question answered:** *"How is this specific product being received? What do people consistently praise, complain about, and how do those signals differ by source?"*

**View:** per-product scorecard with:
- Per-aspect net-sentiment score (mean polarity across mentions) + mention count — **every number drillable to the contributing mentions**
- **Per-aspect intensity distribution** — counts of low / medium / high-intensity mentions on each polarity side. Severity is read directly, not buried inside a weighted average.
- Per-aspect breakdown by source (do Reddit and BestBuy agree on thermals?)
- Verified-purchase share, recency distribution, cross-source coverage per aspect
- Verbatim drill-down: representative positive + negative quotes per aspect, each tagged with source type, verified_purchase where applicable, ownership_duration where applicable, published date, engagement metadata (upvotes / helpful_count where available), and a direct link to the original content
- Lightweight cohort toggles (verified-only vs. all; recent-30d vs. full window)

**Primary audience:** product management (next-refresh priorities), marketing (positioning input).

**Why it matters:** anchors Aspect 2 in a reliable baseline; gives standalone value when a pair's comparative corpus is thin.

### 5.2 Aspect 2 — Comparative deliberation decoder

**Question answered:** *"When public deliberators choose between our product and a competitor's, who wins, and why?"*

**View:** per-pair view with:
- Headline win-rate — of N resolved deliberation threads, % chose each product — **drillable to the contributing threads**
- Top 6–8 ranked reasons per side, with mention counts, intensity context (count of high-intensity reason-mentions), and verbatim examples — **each verbatim carries its source URL and metadata; each reason is drillable to the full set of contributing mentions**
- **Addressability classification per reason** — messaging / software / hardware / pricing — telling the manufacturer what *kind* of fix each reason implies
- Cross-source verification — each reason's presence traced across Reddit, retailer reviews, YouTube, press (where the source covers it)
- Comparative brief (Sonnet-generated) with inline citations: every narrative claim resolves to specific mention IDs

**Primary audience:** execs (structural vs. perception losses), marketing (messaging pivots), product (engineering/software priorities).

**Why it matters:** the differentiating artifact — answers a question neither internal data nor generic social-listening tools can.

## 6. Run model

Every analysis is a reproducible **run** defined by:

- **Product set config** — list of products, with names, aliases, retailer URLs, attribution-regex patterns
- **Pair plan config** — list of product pairs to analyze comparatively (primary-vs-competitor)
- **Source window config** — per-source backfill window (default 6 months) and enable/disable flags
- **Taxonomy version** — which aspect taxonomy + classifier prompts were used

All run outputs — tagged mentions, aggregates, briefs — are stored with run ID and taxonomy version. LLM outputs are cached by content hash × prompt version × model × temperature, making re-runs nearly free and deterministic.

**Incremental update rules:**

| Change | What re-runs |
|---|---|
| Products added | Scrape only new products; all existing mentions and aggregates unchanged |
| Taxonomy version bumped | Re-tag all mentions under the new version; aggregates rebuilt |
| Backfill window extended | Fetch additional months only; existing mentions untouched |
| New source added | Scrape that source; re-aggregate |
| Pair plan edited | Re-aggregate affected pairs only; no re-scrape |

## 7. Success criteria (v1)

### Functional correctness

- Classifier accuracy **≥ 80% loose micro-F1** on aspect tagging, sentiment scoring, and reason tagging (loose = ±1 intensity-bucket tolerance via `compute_micro_f1_loose`; strict tuple match reported alongside but not the gate, per session-37 metric change). Measured against Sonnet-built + operator-spot-checked gold sets.
- Classifier accuracy **≥ 85%** on deliberation thread classification and outcome extraction (binary/multi-class)
- Classifier accuracy **≥ 80%** on intensity tagging (low / medium / high) — measured against the same gold-set methodology
- **≥ 100 usable mentions per pair** in the comparative corpus, so win-rates and ranked reasons aren't anecdotal

### Artifact quality

- Each Aspect 1 scorecard reads as a coherent standalone brief
- Each Aspect 2 pair brief contrast paragraph (session 42 shipped) cites real mention IDs with zero fabrication and frames where each side leads in plain English; **full actionability** (at least one actionable finding with an addressability classification) is gated on the parked full-A2 reason pipeline and tracks corpus deliberation density
- Verbatim evidence is foregrounded on every card — source, verified_purchase, ownership_duration, published_at visible on the quote itself
- **Every UI claim (aggregate number, ranked reason, brief sentence) is traceable to its underlying mentions without manual cross-referencing — evidence-first principle satisfied end-to-end**

### Operational

- Full pipeline runs from config edit to UI render **without manual intervention**
- Re-running with the same config hits the LLM cache — same output, no new cost
- A new product added incurs only incremental scrape + tagging work

## 8. Sources and data scope

| Source | Role | Historical reach (v1) | Library module |
|---|---|---|---|
| Reddit (subreddit sweep + thread fetch) | Primary deliberation signal | 6–12 months via listings + `after` pagination | `scrapers_lib.tier1.reddit` |
| BestBuy paginated reviews | Verified-purchase voice; competitor-mention extraction | All available dated reviews per SKU | `scrapers_lib.tier3.bestbuy` |
| Amazon PDP reviews | Top ~10 verified reviews snapshot | Current top reviews per SKU | `scrapers_lib.tier3.amazon` |
| YouTube transcripts (hand-seeded) | Expert voice; head-to-heads | Full history of seeded videos | `scrapers_lib.tier1.youtube` |
| Gaming-news articles (hand-seeded) | Editorial voice | Full history of seeded articles | `scrapers_lib.tier1.article` |

**Defaults (operator-editable):**
- Reddit subreddits: `r/GamingLaptops`, `r/SuggestALaptop`, `r/pcmasterrace`, `r/buildapc`
- YouTube seed target: ~10–15 videos per pair (head-to-heads + expert single-product reviews)
- Article seed target: ~20–30 articles per pair (roundups + reviews + head-to-heads)
- Language: English only
- Geography: US sources
- Posture: personal research; `robots.txt` honored and rate-limited per library defaults; no sign-in-walled content

## 9. Demo run (v1 validation)

**Product set:**
- **Primaries (Alienware):** 16 Aurora, 16x Aurora
- **Competitors:** ROG Strix G16, ROG TUF 16, Lenovo Legion 5 Pro, Lenovo Legion 7i, HP Omen 16

**Pair plan (default):** all 10 Alienware-vs-competitor pairs (2 × 5). UI pair selector toggles between them. Operator may trim to segment-matched pairs (~5) for tighter compute cost.

**Validation checks:**
- Both UI tabs render for all 7 products and all 10 pairs
- Gold-set eval hits classifier accuracy thresholds
- Each Aspect 2 pair brief surfaces at least one actionable finding
- Re-run with the same config produces identical output from cache

## 10. Constraints and priorities

**Priority order (explicit):** Correctness → Scalability → Maintainability → Speed.

Concretely, this means:
- Full test coverage on the data pipeline + LLM eval harness from day 1
- Type-safe code (mypy), linted (ruff), pre-commit enforced
- All schema changes go through Alembic migrations
- LLM calls are deterministic-ish: `temperature=0`, structured JSON output, versioned prompts
- All classifier outputs cached by content × prompt × model × temp
- Additional weeks are acceptable to meet correctness; shortcuts are not

**Evidence-first:** no claim in the UI exists without traceable evidence. Every aggregate number (sentiment score, mention count, win-rate, reason count) resolves to the contributing mentions; every sentence in a Sonnet-generated brief cites specific mention IDs; every verbatim card surfaces its source type, source URL, and context metadata (verified_purchase, ownership_duration, published_at, author, rating where applicable). LLM-generated text is grounded in stored mentions — verbatim text is rendered from the database, not from the LLM's output, to prevent hallucination from leaking into artifacts. Deleted upstream content is **tombstoned** in local storage so evidence remains visible even after the original is gone, marked with a UI badge indicating deletion state. This principle shapes schema design (aggregates carry mention-ID provenance), LLM prompt contracts (citations required, mention IDs must be real), and UI affordances (every number is drillable).

**Corollary — no hidden weighting formulas.** Every mention counts as 1.0 in sentiment aggregates. Intensity, verified-purchase status, ownership duration, engagement (upvotes / helpful_count), and source type are surfaced *alongside* aggregates (as distributions, shares, per-source breakdowns, and verbatim-card metadata) rather than folded into a single weighted score. Importance emerges from the visible constellation of metrics — intensity distribution + verified share + recency + cross-source coverage — not from a formula the reader cannot re-derive.

**Product-agnostic discipline:** no hard-coded product references in code. All product-specific details (names, URLs, attribution patterns, pair plans) live in config files. The demo run is one application of the engine, not the engine itself.

**Cloud-migration readiness:** every data-layer choice (SQLAlchemy ORM, Alembic migrations, timezone-aware datetimes, JSON columns) is Postgres-compatible. A future cloud migration is a connection-string change + data dump, not a rewrite.

## 11. Timeline

**Estimated effort:** ~7–8 weeks, single operator. Phased with a natural A1-only cutpoint.

| Wave | Duration | Output |
|---|---|---|
| 1 — Foundation | Weeks 1–2 | Config schemas; SQLAlchemy + Alembic setup; all 5 scraper integrations wired; unified corpus in SQLite; LLM routing skeleton; frontend/backend scaffolding |
| 2 — Aspect 1 | Week 3 | Per-SKU aggregation; scorecard view; Sonnet A1 brief. **A1-only cutpoint** — if v1 slips, A1 alone is a defensible ship. |
| 3 — Aspect 2 | Weeks 4–5 | Deliberation classifier; outcome extractor; reason tagger; addressability bucketing; pair view; comparative brief |
| 4 — Eval + polish | Weeks 5–6 | Gold-set construction; regression eval suite; taxonomy iteration; UI polish; design-system pass |
| 5 — Demo run + hardening | Weeks 6–7 | First pilot run on the 7-product demo set; bug-fixes; reproducibility validation |
| Buffer | Week 8 | Slippage absorption; docs refresh |

## 12. Open questions / future work

- **Segmentation project integration.** A separate future project will maintain a catalog of segment-matched SKUs across Alienware and competitors; pulse-check will consume its output as pair plans.
- **Rolling-forward production.** After the v1 demo, running the scheduler continuously to grow the corpus past 6 months is a small additional effort; architecture supports it.
- **Export artifacts.** PDF / markdown brief export is out of scope for v1 but straightforward to add.
- **Multi-category support.** Engine is category-agnostic; taxonomy and seed lists would need adaptation for workstations, monitors, peripherals.
- **Additional source types.** YouTube comments (library doesn't currently fetch), manufacturer forums, Discord communities — potential v1.5 additions.
- **Tombstoning policy.** Partially closed in session 38: tombstoned mentions are **excluded from new aggregations on re-run** (existing aggregates frozen by baked-in mention_ids); UI badge wording is **"link dead"** on `VerbatimCard` tag row 2; conservative detection rule (only HTTP 404 / 410 / DNS-fail / connection-refused write `tombstoned_at`) per ARCH §9. Still open: retention window for tombstoned rows (currently persisted indefinitely), and whether to surface deletion rate as a scorecard quality signal.
