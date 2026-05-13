# pulse-check — Architecture

**Status:** draft &nbsp;·&nbsp; **Paired doc:** [`PRD.md`](PRD.md)

This document describes how pulse-check is put together: the data flow, the module layout, the database schema, the config shapes, the LLM routing and caching contract, the evidence-first implementation, and the incremental re-processing rules. It assumes the PRD's constraints and principles.

---

## 1. Data flow at a glance

```
+-------------------+     +------------------+     +-----------------------+
|   config files    | --> |    scrapers-lib  | --> |   unified SQLite      |
| (products,pairs,  |     |   (fetchers +    |     |   corpus              |
|  source windows)  |     |    attribution)  |     |   (via SQLAlchemy)    |
+-------------------+     +------------------+     +-----------+-----------+
                                                               |
                                                               v
                                                    +----------+-----------+
                                                    |   LOCAL tagging      |
                                                    |   (Qwen 7B, Ollama)  |
                                                    |   - aspect + pol+int |
                                                    |   - deliberation cls |
                                                    |   - outcome + reason |
                                                    |   (all cached)       |
                                                    +----------+-----------+
                                                               |
                                                               v
                                                    +----------+-----------+
                                                    |   aggregation        |
                                                    |   - A1 per-SKU       |
                                                    |   - A2 per-pair      |
                                                    |   (with provenance)  |
                                                    +----------+-----------+
                                                               |
                                                               v
                                                    +----------+-----------+
                                                    |   Sonnet synthesis   |
                                                    |   - verbatim select  |
                                                    |   - addressability   |
                                                    |   - briefs w/cites   |
                                                    +----------+-----------+
                                                               |
                                                               v
                                              +----------------+----------------+
                                              |     FastAPI backend (JSON)      |
                                              +----------------+----------------+
                                                               |
                                                               v
                                              +----------------+----------------+
                                              |   React frontend (Vite + TS    |
                                              |   + Tailwind + shadcn)          |
                                              |   - A1 scorecard tab            |
                                              |   - A2 pair tab w/selector      |
                                              |   - every claim drillable       |
                                              +---------------------------------+
```

Key properties:
- **No LLM calls at UI time.** All tagging, aggregation, and synthesis happen at batch time. The UI reads precomputed results from SQLite via the FastAPI API.
- **Idempotent, reproducible pipeline.** Re-running with the same config + same taxonomy version hits the LLM cache and produces identical output.
- **Unified corpus, pair-plan views.** One scrape across the product set produces one corpus; the pair plan defines which 1v1 views are aggregated and exposed in the UI.

---

## 2. Module layout

```
pulse-check/
├── pulse_check/                 # main Python package
│   ├── config/                  # config loading + validation (product set, pair plan, run config)
│   ├── scraping/                # scrapers-lib integration + orchestration
│   ├── storage/                 # SQLAlchemy models, session management, migrations helpers
│   ├── tagging/                 # LOCAL LLM (Qwen via Ollama) wrappers, prompts, aspect+polarity+intensity classifier
│   ├── synthesis/               # Sonnet/Haiku wrappers: dedup, verbatim selection, addressability, briefs
│   ├── aggregation/             # A1 per-SKU rollup + A2 per-pair rollup; provenance tracking
│   ├── eval/                    # gold-set building, classifier regression tests, eval scripts
│   ├── llm_cache/               # LLM output cache helpers
│   └── api/                     # FastAPI routes: /products, /pairs, /mentions, /aggregates, /briefs
│
├── frontend/                    # React + Vite + TypeScript + Tailwind + shadcn/ui
│   ├── src/
│   │   ├── components/          # shadcn-derived components, verbatim cards, drill-down panels
│   │   ├── pages/               # A1 scorecard page, A2 pair page, pair selector
│   │   ├── lib/                 # API client, data models (TS), theme tokens
│   │   └── styles/              # Tailwind config + Alienware design tokens
│
├── scripts/                     # CLI entry points: scrape, tag, aggregate, build-gold-set, run-eval, run-all
├── alembic/                     # migrations
├── configs/                     # product-set, pair-plan, run-config YAML files (operator-editable)
├── data/                        # all persistent local state — GITIGNORED
│   ├── pulse_check.db           # main analysis DB (mentions, tags, aggregates, briefs, llm_cache)
│   ├── scheduler_state.db       # scrapers-lib Scheduler job queue (resumable scrapes)
│   ├── scrape_cache/            # scrapers-lib HTTP/render cache (raw responses)
│   ├── gold_sets/               # hand-labeled JSON gold sets for classifier eval
│   └── playwright_profiles/     # Playwright persistent profiles (Tier 2/3 stealth)
├── tests/                       # unit + integration + eval
│   ├── unit/
│   ├── integration/
│   └── eval/
├── docs/                        # PRD, ARCHITECTURE, DESIGN_SYSTEM, TESTING, TASKS
├── pyproject.toml
├── alembic.ini
├── .env.example                 # DATABASE_URL, SCRAPE_CACHE_DIR, ANTHROPIC_API_KEY, OLLAMA_HOST
├── .gitignore                   # data/, .venv/, .env, __pycache__/, etc.
└── README.md
```

**Data vs. cache — don't conflate them.** `data/scrape_cache/` is scrapers-lib's internal HTTP cache ("did we already hit this URL?"), managed by the library with its own TTLs. `data/pulse_check.db` is our own structured analytical store ("what did we learn from the data?"), durable and never auto-evicted. They operate at different altitudes and serve different purposes.

**Location is configurable.** `DATABASE_URL` env var (default `sqlite:///data/pulse_check.db`) points at the analysis DB; a future cloud migration is a single env-var change (`postgresql://...`) + `alembic upgrade head` against the new target. Same pattern for `SCRAPE_CACHE_DIR`.

**Why this split:** each package owns one concern with a clean input/output contract. `tagging` and `synthesis` don't know about scraping; `aggregation` doesn't know about LLMs; the API only knows about precomputed rows. Makes each layer unit-testable in isolation and migratable (e.g., swap SQLite→Postgres touches only `storage`).

---

## 3. Data model

SQLAlchemy declarative models, SQLite backend for v1, Postgres-compatible for future cloud migration. Alembic manages schema evolution.

### 3.1 Core tables

**`products`** — the anchor set for a run.
| Column | Type | Notes |
|---|---|---|
| `product_id` | str (PK) | slug; stable across runs |
| `display_name` | str | |
| `brand` | str | |
| `aliases` | JSON | list of alias strings for attribution |
| `attribution_patterns` | JSON | regex patterns (primary + secondary) |
| `urls` | JSON | `{bestbuy, amazon, manufacturer, youtube_seeds[], article_seeds[]}` |
| `created_at` | datetime(tz) | |

**`runs`** — one row per pilot run.
| Column | Type | Notes |
|---|---|---|
| `run_id` | str (PK) | UUID |
| `created_at` | datetime(tz) | |
| `config_snapshot` | JSON | full config at run time |
| `taxonomy_version` | str | e.g. `"v0"` |
| `prompt_versions` | JSON | map of task → prompt hash |

**`mentions`** — durable, run-agnostic. Every raw mention we've ever fetched.
| Column | Type | Notes |
|---|---|---|
| `mention_id` | str (PK) | deterministic hash from scrapers-lib |
| `source_type` | enum | reddit_post / reddit_comment / bestbuy_review / amazon_review / youtube_chunk / article |
| `source_url` | str | |
| `published_at` | datetime(tz) | nullable |
| `author` | str | nullable |
| `raw_text` | text | full mention text — this is what the UI renders |
| `channel` | str | subreddit name or site domain |
| `metadata` | JSON | verified_purchase, ownership_duration, upvotes, helpful_count, rating, parent_id, chunk_start/end, etc. |
| `first_seen_at` | datetime(tz) | |
| `tombstoned_at` | datetime(tz) | nullable; set when upstream content is confirmed gone |
| `tombstone_reason` | str | nullable; e.g. "reddit_404", "bestbuy_removed" |

**`mention_attributions`** — which products a mention is about.
| Column | Type | Notes |
|---|---|---|
| `attribution_id` | int (PK) | |
| `mention_id` | FK → mentions | |
| `product_id` | FK → products | |
| `attribution_type` | enum | primary (fetched for this product) / secondary (text mentions this product) |
| `attribution_method` | enum | regex / url |

A single mention can have multiple attributions (a Reddit thread citing Area-51 18 and Strix G16 gets two rows).

### 3.2 Tagging tables

**`aspect_tags`** — per-mention-aspect polarity + intensity.
| Column | Type | Notes |
|---|---|---|
| `tag_id` | int (PK) | |
| `mention_id` | FK → mentions | |
| `product_id` | FK → products | context — the tag is *about this mention as it relates to this product* |
| `aspect` | enum | the 11 taxonomy buckets |
| `polarity` | enum | negative / neutral / positive |
| `intensity` | enum | low / medium / high |
| `classifier_confidence` | float | |
| `taxonomy_version` | str | |
| `prompt_version` | str | |
| `model` | str | e.g. `"qwen2.5:14b-q4_K_M"` |
| `temperature` | float | 0.0 |
| `created_at` | datetime(tz) | |

Unique constraint: `(mention_id, product_id, aspect, taxonomy_version, prompt_version)`. Re-tagging under a new taxonomy version adds rows; does not overwrite.

**`deliberation_tags`** — thread-level classification for A2.
| Column | Type | Notes |
|---|---|---|
| `tag_id` | int (PK) | |
| `thread_mention_id` | FK → mentions | typically the root post of a Reddit thread |
| `is_deliberation` | bool | |
| `is_resolved` | bool | v2: true iff exactly one of `chosen_product_id` or `chosen_external_name` is set |
| `products_discussed` | JSON | list of product_ids |
| `chosen_product_id` | FK → products | nullable; the tracked winner if resolved (mutually exclusive with `chosen_external_name`) |
| `chosen_external_name` | str(256) | nullable; v2 — free-text name of an untracked external winner (e.g. "Razer Blade 16") when resolved to a product NOT in the tracked universe; mutually exclusive with `chosen_product_id` |
| `prompt_version` | str | |
| `model`, `temperature`, `created_at` | | |

**`reason_tags`** — per-mention reasoning within a deliberation thread (for A2 reason buckets).
| Column | Type | Notes |
|---|---|---|
| `tag_id` | int (PK) | |
| `mention_id` | FK → mentions | the comment expressing a reason |
| `thread_mention_id` | FK → mentions | parent thread |
| `winning_product_id` | FK → products | which product the reasoning favors |
| `reason_bucket` | enum | same 11 aspects + extras (`brand_loyalty`, `value_deal`, `support_reputation`, `prior_ownership`) |
| `polarity` | enum | |
| `intensity` | enum | |
| `prompt_version`, `model`, `temperature`, `created_at` | | |

### 3.3 Aggregate tables (evidence-first)

Every aggregate row carries its provenance — the list of contributing mention IDs — so every number in the UI is drillable.

**`aggregates_aspect_sku`** — A1 scorecard data per (run, product, aspect).

Two parallel buckets are written per row: a **PRIMARY** bucket (legacy columns, drives the brief body and citations) and a **SECONDARY** bucket (`*_secondary` mirror columns, surfaces comment-inheritance density and other secondary-attribution signal). The same eight-field arithmetic runs twice — once on PRIMARY-attributed mentions, once on SECONDARY-only — and both halves write into the same row. A row is written whenever **either** bucket has at least one contribution; the empty side carries zero/empty values. PRIMARY/SECONDARY are bucketed, never combined: aggregating across them is left to the consumer (UI / brief / operator), preserving the no-hidden-weighting principle. See §7.1.

| Column | Type | Notes |
|---|---|---|
| `aggregate_id` | int (PK) | |
| `run_id` | FK → runs | |
| `product_id` | FK → products | |
| `aspect` | enum | |
| `total_mentions` | int | PRIMARY bucket count |
| `polarity_counts` | JSON | PRIMARY: `{negative, neutral, positive}` |
| `net_sentiment` | float | PRIMARY: mean polarity, −1 to +1; `0.0` if bucket empty |
| `intensity_counts` | JSON | PRIMARY: `{low, medium, high}` |
| `verified_share` | float | PRIMARY: 0.0–1.0; share of contributing mentions that are `verified_purchase=True` |
| `by_source` | JSON | PRIMARY: per-source-type: `{total, polarity_counts}` |
| `by_recency` | JSON | PRIMARY: `{0_30, 30_90, 90_180, 180_plus, unknown}` bucket counts |
| `mention_ids` | JSON | **PRIMARY provenance — full list of contributing mentions** |
| `total_mentions_secondary` | int | SECONDARY bucket count |
| `polarity_counts_secondary` | JSON | SECONDARY parity |
| `net_sentiment_secondary` | float | SECONDARY parity; `0.0` if bucket empty |
| `intensity_counts_secondary` | JSON | SECONDARY parity |
| `verified_share_secondary` | float | SECONDARY parity; `0.0` if bucket empty |
| `by_source_secondary` | JSON | SECONDARY parity |
| `by_recency_secondary` | JSON | SECONDARY parity |
| `mention_ids_secondary` | JSON | **SECONDARY provenance** |
| `computed_at` | datetime(tz) | |

**`aggregates_pair_reason`** — A2 ranked reasons per (run, pair, winning_product, reason_bucket).
| Column | Type | Notes |
|---|---|---|
| `aggregate_id` | int (PK) | |
| `run_id` | FK → runs | |
| `pair_id` | str | e.g. `"alienware_16_aurora_vs_rog_strix_g16"` |
| `winning_product_id` | FK → products | |
| `reason_bucket` | enum | |
| `total_mentions` | int | |
| `intensity_counts` | JSON | |
| `addressability` | enum | messaging / software / hardware / pricing / mixed (Sonnet-assigned) |
| `addressability_rationale` | text | Sonnet's one-line justification |
| `representative_mention_ids` | JSON | Sonnet-selected verbatims (IDs only) |
| `mention_ids` | JSON | **full provenance** |
| `computed_at` | datetime(tz) | |

**`pair_win_rates`** — A2 headline per (run, pair).
| Column | Type | Notes |
|---|---|---|
| `aggregate_id` | int (PK) | |
| `run_id` | FK → runs | |
| `pair_id` | str | |
| `product_a_id`, `product_b_id` | FK → products | |
| `total_resolved_threads` | int | |
| `a_wins`, `b_wins`, `ties` | int | |
| `thread_mention_ids` | JSON | **provenance — the threads** |
| `computed_at` | datetime(tz) | |

**`briefs`** — Sonnet-generated narratives with citations.
| Column | Type | Notes |
|---|---|---|
| `brief_id` | int (PK) | |
| `run_id` | FK → runs | |
| `scope_type` | enum | aspect_1_sku / aspect_2_pair |
| `scope_id` | str | `product_id` or `pair_id` |
| `narrative` | JSON | array of `{claim_text, cited_mention_ids[]}` — see §6.3 |
| `generated_at` | datetime(tz) | |
| `prompt_version`, `model` | str | |

### 3.4 LLM cache

**`llm_cache`** — generic, task-agnostic cache.
| Column | Type | Notes |
|---|---|---|
| `cache_key` | str (PK) | `sha256(input_hash + prompt_version + model + temperature)` |
| `input_hash` | str | `sha256(input_payload)` |
| `prompt_version` | str | |
| `model` | str | |
| `temperature` | float | |
| `raw_output` | text | |
| `parsed_output` | JSON | nullable |
| `created_at` | datetime(tz) | |

All LLM calls (LOCAL, Sonnet, Haiku) go through a wrapper that checks this table first. Nothing is evicted. A prompt-version bump or model-swap creates new rows; old rows remain for audit and diff.

### 3.5 Schema evolution

Alembic migration file per change. The migrations directory is versioned alongside code. `alembic upgrade head` runs pending migrations; `downgrade` reverses them. This is the only supported way to change schema — never edit tables by hand.

---

## 4. Config shapes

All configs are YAML files in `configs/`. Loaded and validated via Pydantic v2 models at run start; validation errors abort the run with a clear message.

### 4.1 Product set config

```yaml
# configs/product_set_gaming_laptops_2026.yaml
products:
  - product_id: alienware_16_aurora
    display_name: "Alienware 16 Aurora"
    brand: "Alienware"
    aliases:
      - "16 Aurora"
      - "Alienware Aurora 16"
      - "Aurora 16"
    attribution_patterns:
      primary:
        - "\\balienware\\s+16\\s*aurora\\b"
        - "\\baurora\\s+16\\b"
    urls:
      bestbuy: "https://www.bestbuy.com/site/alienware-16-aurora-..."
      amazon: "https://www.amazon.com/dp/B0..."
      manufacturer: "https://www.dell.com/en-us/shop/dell-laptops/..."
      youtube_seeds:
        - "https://www.youtube.com/watch?v=..."
        - "..."
      article_seeds:
        - "https://www.notebookcheck.net/..."
        - "..."

  - product_id: rog_strix_g16
    display_name: "ROG Strix G16"
    # ...
```

### 4.2 Pair plan config

```yaml
# configs/pair_plan_alienware_vs_all.yaml
pairs:
  - pair_id: alienware_16_aurora_vs_rog_strix_g16
    primary: alienware_16_aurora
    comparator: rog_strix_g16
  - pair_id: alienware_16_aurora_vs_rog_tuf_16
    primary: alienware_16_aurora
    comparator: rog_tuf_16
  # ... 10 pairs total for the demo run
```

### 4.3 Run config

```yaml
# configs/run_demo_2026_04.yaml
run_id: demo_2026_04
product_set: configs/product_set_gaming_laptops_2026.yaml
pair_plan: configs/pair_plan_alienware_vs_all.yaml
source_windows:
  reddit:
    enabled: true
    backfill_months: 6
    subreddits: [GamingLaptops, SuggestALaptop, pcmasterrace, buildapc]
  bestbuy_reviews:
    enabled: true
    paginate: true
    backfill_months: 6
  amazon_reviews:
    enabled: true
    # Amazon PDP is snapshot-only (top ~10 inline); window not meaningful
  youtube:
    enabled: true
    backfill_months: 6   # filters by video published_at
  article:
    enabled: true
    backfill_months: 6
taxonomy_version: v0
```

### 4.4 Adding a new source later

New source = add a new top-level entry under `source_windows` with its own `enabled`, `backfill_months`, and source-specific fields; no schema change required. Per-source backfill windows are independent — thin-signal sources can run at 12 months while dense ones stay at 3.

---

## 5. Attribution strategy

Attribution is the act of linking a mention to the product(s) it's about. Two passes:

**Primary attribution (at fetch time).** When scrapers-lib fetches from a URL known to belong to a product (e.g., BestBuy reviews for SKU X, a YouTube video URL seeded under product Y), the fetcher attributes results to that product directly. When fetching from a discovery source (subreddit sweep, article seed), the fetcher uses each product's `attribution_patterns.primary` via `attribute_regex_all` to generate one mention per matching product.

**Secondary attribution (post-fetch).** After each scrape, a secondary pass runs every stored mention's `raw_text` through **all products' patterns** (primary + an optional looser `secondary` pattern list). Matches produce `mention_attributions` rows with `attribution_type = secondary`. This catches cases like a BestBuy Area-51 18 review whose body mentions "ROG Strix" — the review's primary attribution is Area-51, the secondary attribution is Strix G16, and the mention is therefore a candidate for Aspect 2's "considered" corpus for that pair.

**Tertiary attribution — comment inheritance (post-fetch).** A third pass runs after secondary attribution: unattributed Reddit comment mentions inherit their parent post's PRIMARY attributions as SECONDARY (`attribution_type = secondary`, `attribution_method = regex` for schema uniformity even though the link is structural, not a regex match on the comment text). The link is `mention.metadata_["parent_id"]` matching the parent post in the form `t3_<post_id>`. Rationale: a comment in a thread whose post is primary-attributed to product P is at least about-P-discussion, even if the comment text doesn't repeat the per-comment anchor regex. Skipped silently when the parent post is not in our DB. Implemented in `pulse_check/scraping/comment_inheritance.py`, called from `run_scrape` after `apply_secondary_attribution`. Comments fetched in this mode bypass scrapers-lib's strict per-comment anchor regex via `fetch_reddit_comments(emit_all_comments=True)`. This is a structural attribution mechanism, not text-based; comments not under one of our primary-attributed posts produce no attribution.

**Definitional default — "considered mention":** review body contains a comparator-anchor secondary attribution. The operator can refine attribution patterns iteratively; every scrape re-runs secondary attribution against the current pattern set, so refinements propagate without re-scraping.

---

## 6. LLM routing and contracts

Three models, three tiers of work.

### 6.1 LOCAL — Qwen 7B via Ollama

Batch-time, high-volume classification. Every call: `temperature=0`, structured JSON output (Ollama's `format=json` or explicit schema), versioned prompt strings, cached.

| Function | Input | Output |
|---|---|---|
| `tag_mention_aspects(mention_text, product_context)` | mention text + the product it's attributed to | list of `{aspect, polarity, intensity, confidence}` — multi-label; empty list is valid |
| `classify_deliberation_thread(thread, products)` | role-segmented `DeliberationThread` (OP post + optional OP edit + OP top-level comments + other top-level comments) + tracked-product universe `tuple[ProductContext, ...]` | `{is_deliberation: bool, is_resolved: bool, products_discussed: [product_id str], chosen_product_id: product_id str \| null, chosen_external_name: str \| null, confidence: float \| null}` |
| `tag_reasons(comment_text, context)` | comment text + `ThreadContext` (winning product id + display_name + OP post text + the `tuple[ProductContext, ...]` of products debated in the thread) | list of `{reason_bucket, polarity, intensity}` |

**Deliberation input is role-segmented**, not flat thread text, so the OP-only resolution rule (§11) is enforced structurally: the prompt renders OP segments under `[OP_POST] / [OP_EDIT] / [OP_COMMENT n]` markers and other-commenter segments under `[OTHER_COMMENT n]`. The rule line in the prompt explicitly blocks `[OTHER_COMMENT]` assertions from resolving the thread. `thread_id` and per-product `display_name` are excluded from the cache key — same content + same product_id set rehydrate without re-classifying.

**Winner has two channels (v2):** `chosen_product_id` for tracked winners (must be a `product_id` from `products_discussed`); `chosen_external_name` as free-text for untracked winners ("the Razer Blade 16", "MSI Stealth 16 AI Studio"). The two are **mutually exclusive** — at most one is set per thread. `is_resolved` holds iff exactly one is set. External winners surface the "tracked product was considered but lost to X" signal that v1's tracked-only schema dropped; tracked-only consumers (e.g. the reason-tagging gate in `deliberation_gold_set.py`) still filter on `chosen_product_id is not None` and silently skip external-winner threads. Free-text representation (not normalized via a known-untracked-products list) is deliberate — clusters can be derived post-hoc if patterns emerge, and the curation burden of maintaining an external-product index is avoided.

**Reason-tagger input is comment-scoped with a bundled `ThreadContext`** rather than three positional args, so callers (batch driver, eval runner) pass one dataclass per thread and reuse it across the thread's comments. The context bundles the winning product (id + display_name) + the OP post + the products_discussed list; polarity in the output is relative to the *winning* product, so dissent ("would've gone with the Blade for thermals") and endorsement ("Strix nailed the thermals") both surface `thermals` as a deliberation criterion with the appropriate sign. `winning_product_display_name` and per-product `display_name` strings render in the prompt but are excluded from the cache key — same comment + same product_id set rehydrate without re-tagging. Output schema is strict three-field `{reason_bucket, polarity, intensity}`: no `confidence` here (the aspect + deliberation classifiers emit one; reason tagging does not — adding it requires a `PROMPT_VERSION` bump).

Cache key: `sha256(input_payload + prompt_version + "qwen2.5:7b-q4_K_M" + "0.0")`.

Throughput budget: ~60–120 tok/s on RTX 5070; a ~5,000-mention corpus tags in 20–60 min. VRAM footprint ~4–5GB (Q4_K_M).

**Per-task fallback:** if gold-set eval shows Qwen 7B misses threshold on a specific task (most likely candidates: deliberation classification, reason tagging on nuanced cases), that task swaps to Haiku via the same cached-call contract — cache key changes, no pipeline disruption. Routing is per task, not wholesale.

> **Deviation in effect (Wave 2):** `tag_mention_aspects` and `classify_content_type` currently run on Haiku, not Qwen — see §6.5 for the full table.

### 6.2 Sonnet — synthesis + eval

Low-volume, quality-sensitive work. Every call cached.

| Function | Input | Output | When |
|---|---|---|---|
| `build_aspect_gold_set(mentions, taxonomy)` | sample of 100–200 mentions | hand-spot-checkable JSON of `{mention_id, aspect_tags[]}` | Operator-triggered; for gold-set construction |
| `classify_addressability(reason_bucket, sample_verbatims, winning_product)` | reason bucket + ~5 sample verbatims | `{category: messaging/software/hardware/pricing/mixed, rationale: str}` | Per reason per pair during aggregation |
| `select_verbatims(mention_pool, count, criteria)` | mention IDs + text + metadata + selection criteria | list of **mention IDs only** | For each aggregate row; UI renders text from DB |
| `write_a1_brief(product_id, aggregates, sample_verbatim_ids)` | per-product aggregate rows + a sample of mentions for grounding | structured narrative (see §6.3) | Per product per run |
| `write_a2_brief(pair_id, win_rates, ranked_reasons, sample_verbatim_ids)` | per-pair aggregate rows + sample mentions | structured narrative | Per pair per run |

### 6.3 Sonnet citation contract

Briefs must cite evidence for every claim. Sonnet is prompted to return a structured JSON output:

```json
{
  "brief_title": "...",
  "sections": [
    {
      "heading": "Top losing reasons",
      "claims": [
        {
          "claim_text": "Thermals is the top-cited reason deliberators chose the Strix G16 over the Area-51 18, appearing in 60 resolved threads.",
          "cited_mention_ids": ["m_abc123", "m_def456", "m_ghi789"]
        }
      ]
    }
  ]
}
```

Post-generation validation (soft-warn, operator-locked session 12 — see "Validation output" below):
1. Every `cited_mention_ids` entry must resolve to a real `mentions.mention_id`. **Retry policy:** on `fabricated_ids` only, the orchestrator re-calls the brief writer once with `prompt_version = a1_brief_v1_strict` (a stricter preamble emphasizing fidelity to provided verbatims) and re-validates. Other warning channels do not retry. An empty `cited_mention_ids` list is permitted only for the explicit placeholder claim defined under "A1 brief layout" below.
2. The cited mentions must actually be in the input pool the selector was given (`allowed_pool` = PRIMARY ∪ SECONDARY mention IDs across all aspects of the product) — no cross-product / cross-run leakage.
3. If a claim carries a specific count paired with a count-noun ("60 threads", "10 users"), the citation validator regex-extracts the integer and compares it to the matched aggregate's mention count for the appropriate bucket (PRIMARY for §1/§2 claims, SECONDARY for §3/§4). Drift > ±5% is flagged as a soft-warn — not blocking. Pattern: `\d+\s+(user|mention|thread|reviewer|comment|post|review|owner|customer|complaint|complain|praise|report)s?` (case-insensitive).
4. Empty claims (cited_mention_ids = []) outside the §6.3 placeholder are flagged.

This structure renders naturally in the UI: each `claim_text` is one sentence or paragraph; hovering or clicking it opens a panel with the cited mentions as drillable cards.

**A1 brief layout (operator-locked, session 11).** The contract above is generic; the A1 brief uses four sections in fixed order, prompt_version `a1_brief_v1`:

| # | Heading | Inclusion rule | Cap |
|---|---|---|---|
| 1 | High-confidence strengths | aspects with PRIMARY positive ≥ 3, ranked by count desc | up to 3 aspects |
| 2 | High-confidence weaknesses | aspects with PRIMARY negative ≥ 3, ranked by count desc | up to 3 aspects |
| 3 | Low-signal strengths (public chatter) | aspects with SECONDARY positive ≥ 1 not in §1, ranked by count desc | up to 3 aspects |
| 4 | Low-signal weaknesses (public chatter) | aspects with SECONDARY negative ≥ 1 not in §2, ranked by count desc | up to 3 aspects |

One claim per aspect per section. Each claim cites up to 3 mentions for that aspect — PRIMARY for sections 1–2, SECONDARY for sections 3–4 — selected by the deterministic verbatim selector (`pulse_check.synthesis.selector`), which ranks `aspect_tags.intensity` desc (high > medium > low) and dedups by cluster (see §6.4). The brief writer assembles `cited_mention_ids` from the selector's output and never receives mention IDs from Sonnet — Sonnet writes only `brief_title` and per-`(quadrant, aspect)` `claim_text`. No padding: sections render with fewer than the cap when the data doesn't support more.

**Empty section 2 — placeholder rule.** When zero aspects qualify for high-confidence weaknesses, section 2 still renders with one placeholder claim: `claim_text = "No top-of-mind criticism in PRIMARY chatter — see §4 below"`, `cited_mention_ids = []`. This is the sole case where an empty citation list is contractually permitted (see validation rule 1).

**Validation output (operator-locked, session 12).** The four citation-integrity checks (above) run post-generation as a soft-warn — the brief is persisted whether or not warnings fire. The final `ValidationResult` is persisted as a top-level `flagged_citation_issues` key on `briefs.narrative` JSON; downstream UI reads this to badge briefs that have warnings. All-quadrants-empty short-circuits Sonnet entirely (brief title `"{display_name} — A1 voice"` + Q2 placeholder section only; no LLM call).

### 6.4 Haiku — near-duplicate dedup

Before Sonnet selects verbatims, Haiku clusters near-identical mentions (copy-paste / same-user-double-post / paraphrase) so Sonnet doesn't pick three versions of the same quote. Simple contract:

| Function | Input | Output |
|---|---|---|
| `cluster_near_duplicates(mentions)` | list of `{mention_id, raw_text}` | list of cluster IDs — mentions with the same cluster ID are near-duplicates |

Sonnet then sees one representative per cluster. Haiku is also cached.

### 6.5 Haiku — batch classifiers (per-task fallback per §6.1)

Two batch classifiers originally specced for Qwen now run on Haiku, against the same `call_with_cache` contract. The swap was operator-confirmed during Wave 2 build-out (Qwen 7B latency + parse-error rate on long inputs in early gold-set eval). Per-task fallback per §6.1, applied wholesale to these tasks:

| Function | Model | Input | Output |
|---|---|---|---|
| `tag_mention_aspects(mention_text, product_context)` | Haiku | mention text + attributed product | list of `{aspect, polarity, intensity, confidence}` (deduped within-response on aspect; Haiku occasionally re-emits) |
| `classify_content_type(mention_text)` | Haiku | mention text | `{content_type: review \| deal \| other, confidence}` |

Cache keys substitute the Haiku model name; downstream contracts and prompt-version semantics unchanged. No other LLM-routing assumptions are affected.

---

## 7. Aggregation layer

Aggregation is deterministic given (mentions + tags + run config). No LLM calls in aggregation itself — addressability and verbatim selection are Sonnet steps that *feed into* aggregate rows, but the rollup arithmetic is plain SQL.

### 7.1 Aspect 1 aggregation (per SKU)

For each (product, aspect) pair in the run:
1. Fetch all `aspect_tags` where `product_id = P`, `aspect = A`, `taxonomy_version = run.taxonomy_version`, `prompt_version = run.prompt_version`. **Partition by attribution into two buckets:** PRIMARY-attributed → primary bucket; SECONDARY-only attributed → secondary bucket. A `(mention, product)` pair with both PRIMARY and SECONDARY rows lands in the primary bucket only — no double-count, preserving "every mention = 1.0".
2. **Run the same eight-field computation twice — once per bucket:** `total_mentions`, `polarity_counts`, `net_sentiment = (positive − negative) / total_mentions` (or `0.0` if bucket empty), `intensity_counts`, `verified_share`, `by_source`, `by_recency`, plus `mention_ids` provenance.
3. Write one `aggregates_aspect_sku` row carrying both buckets — primary fields and `*_secondary` fields. A row is emitted when either bucket has at least one contribution; the empty side carries zero/empty fields. Idempotent rerun via delete-then-insert keyed on `(run_id, product_id)`.
4. Sonnet selects ~6 representative verbatims per aspect **from the PRIMARY bucket only** (3 positive, 3 negative, biased toward high-intensity). `representative_mention_ids` stored on the aggregate (or a sibling table if preferred). Citations stay primary-only; the SECONDARY count is surfaced as a sidebar number to the operator (preview brief and downstream UI).
5. Sonnet writes the A1 brief for the product (§6.3 contract), citing specific mention IDs from the PRIMARY bucket.

### 7.2 Aspect 2 aggregation (per pair)

For each pair in the pair plan:
1. **Find resolved deliberation threads** covering this pair: `deliberation_tags` where `is_resolved = True` and both products are in `products_discussed`.
2. **Win-rate:** count `chosen_product_id = A` vs `= B`; write `pair_win_rates` row with `thread_mention_ids`. Resolved-to-external threads (`chosen_external_name` set, `chosen_product_id` null) are excluded from this pair aggregate by construction and surface separately via a future `lost_to_external` aggregate (v2 lays the schema; no aggregator yet).
3. **Reason buckets:** gather `reason_tags` from comments within resolved threads, grouped by `(winning_product_id, reason_bucket)`.
4. For each bucket with count ≥ small floor: compute `total_mentions`, `intensity_counts`, collect `mention_ids`.
5. Sonnet classifies `addressability` for each bucket using a sample of verbatims.
6. Haiku dedups near-duplicate verbatims.
7. Sonnet selects representative verbatims per bucket.
8. Write `aggregates_pair_reason` rows.
9. Sonnet writes the A2 brief for the pair with the citation contract.

### 7.3 Considered-mention corpus (A2 cross-source enrichment)

For each pair, in addition to Reddit deliberation threads, gather:
- BestBuy / Amazon reviews of product A whose body mentions B (via secondary attribution)
- BestBuy / Amazon reviews of product B whose body mentions A
- YouTube transcript chunks from seeded head-to-head videos
- Articles comparing the two

These feed the "cross-source verification" column for each reason bucket — a reason bucket is flagged as cross-source-verified if it appears in at least two source types.

---

## 8. Evidence-first in practice

The evidence-first principle manifests at four layers:

1. **Schema.** Every aggregate row carries `mention_ids` as a provenance array. Dropping an aggregate loses the number; but the mentions remain, and the aggregate is recomputable.
2. **LLM contract.** Sonnet outputs citation-structured JSON; the generator validates every cited ID against the `mentions` table before the brief is accepted.
3. **UI rendering.** Verbatim text on cards is fetched from `mentions.raw_text`, not from Sonnet's output. Sonnet decides which mentions to cite; the database provides the actual text. A hallucinated quote is structurally impossible.
4. **Drill-through.** Every aggregate number on the scorecard has a "show evidence" affordance that opens a panel with the mention cards. Every sentence in a brief has a citation popover.

Every mention card displays:
- Source type icon + name (Reddit / BestBuy / Amazon / YouTube / Article)
- Source URL (clickable, opens upstream)
- `verified_purchase` chip (where applicable)
- `ownership_duration` chip (where applicable, e.g. "6 months")
- Publish date
- Author (where public)
- Engagement: upvotes (Reddit), helpful_count (BestBuy), rating (where given)
- The raw text itself
- Aspect tags with polarity + intensity
- **Tombstone badge** if `tombstoned_at` is set ("no longer available on source — retained locally")

---

## 9. Tombstoning and upstream deletion

**Detection.** A lightweight `verify_mentions` job periodically re-fetches a sampled subset of stored mentions (or checks HTTP status of their source_url) and marks `tombstoned_at` + `tombstone_reason` for those returning 404 / not-found / deleted.

**Effect on aggregates.** Tombstoned mentions remain in the corpus and remain contributors to aggregates — the aggregate was computed from them; removing them retroactively would change published numbers. They're shown in the UI with a deletion badge.

**Operator policy (to nail down during implementation, §12 of PRD):** retention window, whether to exclude tombstoned mentions from *new* aggregations on re-run, and whether to include deletion rate as a quality signal on the scorecard.

---

## 10. Incremental re-processing rules

pulse-check is designed so that each config change triggers the minimum necessary re-work. The `llm_cache` + mention-durability design makes most re-runs cheap.

| Change | What re-runs |
|---|---|
| **Product added** | Scrape new product's sources; secondary attribution over existing mentions against the new product's patterns; aspect-tag any newly attributed mentions; re-aggregate affected rows |
| **Product removed** | Aggregates filtered at query time; no re-scrape. Stored mentions remain. |
| **Taxonomy version bumped** | All aspect + reason tagging re-runs under new taxonomy_version (cache key differs — cold cache for new version). Mentions, attributions, deliberation tags untouched. Aggregates rebuild. |
| **Classifier prompt tweaked (prompt_version bump)** | Re-tag only what changed; cache-miss for new prompt_version. Validate via gold-set eval before accepting. |
| **Backfill window extended** | Fetch older content per source; existing mentions + tags untouched. Aggregate rebuild. |
| **New source type added** | Scrape only that source; primary + secondary attribution for new mentions; tag; aggregate. |
| **Pair plan edited** | Re-aggregate affected pairs only; no re-scrape, no re-tagging. |
| **Sonnet brief prompt changed** | Re-run brief generation only; aggregates untouched. |

---

## 11. Definitional defaults

These are the concrete rules pulse-check uses to interpret data. They live in prompts + code; operators refine iteratively during and after the pilot.

- **Resolved deliberation thread:** the OP either (a) edits the original post to name the chosen product, or (b) posts a top-level comment themselves in the thread naming the chosen product. Third-party declarations ("I think OP went with X") do not resolve.
- **Considered mention:** a review whose `raw_text` produces a secondary attribution against a product other than its primary.
- **High-intensity mention:** anchor examples per aspect are included in the classifier prompt; strong-language / quantified / severity-tagged language triggers high. Low-intensity: passing mentions, mild language. The anchor examples are part of the prompt_version and are tuned against the gold set.
- **Cross-source-verified reason:** a reason bucket that appears in at least two distinct `source_type` values.
- **Usable mention (for the ≥ 100 per-pair threshold):** any mention attributed to either product in the pair with at least one aspect tag or one deliberation/reason tag.

---

## 12. Key trade-offs and why

- **SQLite v1 backend, Postgres-compatible.** Low setup cost, single-user-friendly, well-supported by SQLAlchemy + Alembic. A future cloud deployment swaps the connection string. Cost: SQLite's concurrency weakness doesn't matter for single-operator batch workloads.
- **Precomputed aggregates vs. on-demand compute.** Precomputed. UI is instant, re-runs are cached, numbers are reproducible. Cost: any UI-level filter we haven't precomputed isn't interactive. Mitigation: precompute the commonly-needed cohort splits (verified, recent) upfront.
- **One unified corpus vs. per-pair corpora.** Unified. One scrape serves every 1v1, and secondary attribution captures cross-product mentions naturally. Cost: the corpus has more rows than any single pair needs; queries filter. Worth it.
- **LLM citation contract vs. free-form briefs.** Citation. Makes hallucination structurally hard and evidence-first enforceable. Cost: slightly more complex prompt + output-validation step. Worth it.
- **No hidden weighting in aggregates.** Every mention = 1.0. Intensity, verified status, recency, engagement are shown alongside rather than folded in. Cost: the reader has to look at multiple numbers to judge importance. Benefit: no contested-formula objections; every score is auditable in 10 seconds.
- **No LLM at UI time.** All synthesis happens at batch time; UI is read-only on precomputed rows. Cost: changing the brief wording requires re-running. Benefit: UI is fast, deterministic, cheap to serve.
- **Text rendered from DB, not LLM output.** Sonnet picks IDs; DB provides text. Cost: two-step rendering. Benefit: quotes are always real, and tombstoning works transparently.

---

## 13. Operator workflow

For reference, the CLI flow a single operator follows to produce a full run:

```bash
# One-time setup per environment
alembic upgrade head                              # apply migrations

# Per run (from a fresh config)
scripts/scrape.py      --run-config configs/run_demo_2026_04.yaml
scripts/tag.py         --run-config configs/run_demo_2026_04.yaml
scripts/aggregate.py   --run-config configs/run_demo_2026_04.yaml
scripts/synthesize.py  --run-config configs/run_demo_2026_04.yaml
scripts/serve.py                                  # FastAPI + frontend dev server

# Evaluation (before merging a prompt change)
scripts/build-gold-set.py  --task aspect_tagging  --sample-size 150
scripts/run-eval.py        --task aspect_tagging  --against-gold-set gold_v1.json
```

Each script is idempotent — re-running after partial failure picks up where it left off via the LLM cache and durable mentions.
