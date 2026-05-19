# pulse-check

**Status:** v1 pilot artifact substantively complete &nbsp;·&nbsp; **Demo run:** `run_wave5_v1` (53 of 59 gaming laptops briefed)

A product-listening pilot engine for PC manufacturers. Takes a configured set of products, pulls public commentary about each (Reddit, retailer reviews, YouTube, gaming press), and produces a webapp with three exec-oriented views:

- **Standalone voice** — per-product aspect scorecard showing what buyers and reviewers consistently praise or complain about, with a Sonnet-written brief that cites real mention IDs.
- **Head-to-head comparison** — pick any two tracked products; see aspect-by-aspect where each one leads on net sentiment, with the underlying quotes one click away.
- **Cross-product heatmap** — every tracked product across every aspect on one screen, tinted by sentiment, every cell drillable to verbatims.

Product-agnostic engine. Alienware gaming laptops are the first demo product set; the same engine runs any product set through the same analysis.

Comparative deliberation decoder (A2 — "why people choose one over another") is deferred to a future wave; the corpus on the v1 demo set has too few resolved deliberation threads to drive a reliable artifact (see [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md) sessions 29–30).

---

## What it does

- **Fetches** public commentary via [`scrapers-lib`](../scrapers-lib) across Reddit, BestBuy paginated reviews, Amazon PDP reviews, YouTube transcripts, and gaming-news articles.
- **Attributes** every mention to one or more products via configurable regex patterns at fetch time + a post-fetch secondary sweep.
- **Triage-classifies** every mention as `review` / `deal` / `other` via Haiku so downstream synthesis can filter out price-deal noise.
- **Aspect-tags** each surviving mention for 11 aspects (thermals, performance, keyboard, display, battery, build_quality, software_experience, price_value, support_warranty, aesthetics, portability) with polarity and intensity via Haiku.
- **Aggregates** per-product per-aspect rollups (mention counts, net sentiment, mention IDs).
- **Synthesizes** A1 product briefs with Sonnet under a strict citation contract — every claim resolves to specific mention IDs in storage, and the renderer pulls verbatim text from the DB, never from LLM output.
- **Serves** a FastAPI + React webapp where every number drills down to its evidence; every verbatim carries its source URL + metadata.

## What it doesn't do

See [`docs/PRD.md` §4.2 Non-goals](docs/PRD.md). Highlights:

- Not a consumer-facing buying tool.
- Not a real-time monitoring dashboard (v1 runs analyses on demand; quarterly refresh is the operational cadence).
- Not a general brand-sentiment tool; every analysis is product-set-scoped.
- No PDF/markdown export, no mobile, no multi-user auth.

---

## Prerequisites

- **Python 3.12**, PowerShell or git-bash on Windows
- **Node.js 20+** + `npm`
- **[Anthropic API key](https://console.anthropic.com)** — Haiku for tagging, Sonnet for briefs
- **[scrapers-lib](../scrapers-lib) ≥ 1.4.0** installed editable in the same Python environment
- **(Optional) [Ollama](https://ollama.com)** with `qwen2.5:7b-q4_K_M` pulled — for the Qwen local-tagging path. Haiku is the default production path on the v1 demo set; Qwen support is plumbed but not active by default.
- **(Optional) [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)** — for sharing the running webapp on a public URL without exposing your machine directly. Maps `/pulse-check` → `localhost:8765`.

Hardware baseline: any modern laptop. A GPU is only relevant if you use the optional Qwen local-tagging path.

## Install

```powershell
# From this project directory
python -m venv .venv
.venv\Scripts\activate           # PowerShell on Windows

# Install pulse-check (editable) + scrapers-lib (editable from sibling dir)
pip install -e .
pip install -e ../scrapers-lib
playwright install chromium      # for scrapers-lib Tier 2/3 sources

# Frontend
cd frontend && npm install && cd ..

# Env
copy .env.example .env           # then edit with your Anthropic key

# Database
.venv\Scripts\python -m alembic upgrade head
```

---

## Run a pilot

The orchestrators (`run_stage_a.py` / `run_stage_b.py`) are the happy path. They chain tagging → aggregation → brief synthesis under one run_id with the right commit cadence so a crash mid-run never loses paid LLM calls. Granular per-stage scripts are documented further down for advanced cases.

```powershell
# 1. Configure — start from the active wave config or copy your own
#    configs/run_wave5_v1.yaml is the working v1 demo config
notepad configs/run_wave5_v1.yaml

# 2. Scrape — patient; one full Wave 5 scrape took ~hours
.venv\Scripts\python scripts/scrape.py --run-config configs/run_wave5_v1.yaml

# 3. Triage every mention as review / deal / other (prerequisite for tagging)
.venv\Scripts\python scripts/classify_content_type.py --run-config configs/run_wave5_v1.yaml

# 4. Stage A — tag + aggregate + brief the 3 anchor products (Alienware 16
#    Aurora, ROG Strix Scar 16, HP Omen Max 16). Fast (~17 min on the demo
#    set) — sanity-check the pipeline before committing to the full corpus.
.venv\Scripts\python scripts/run_stage_a.py

# 5. Stage B — same loop on the remaining 56 products. Wall-clock ~90 min,
#    ~$10–11 in LLM spend on the demo set. Use --commit-every to preserve
#    paid calls if the run is killed mid-flight.
.venv\Scripts\python scripts/run_stage_b.py --commit-every 50

# 6. Serve — build the frontend, run the unified FastAPI server on :8765
.venv\Scripts\python scripts/serve_public.py
# Open http://localhost:8765
```

Re-running with the same config hits the LLM cache (`(content_hash, prompt_version, model, temperature)`) and the scrape cache. Outputs are byte-identical.

### Granular controls

If you need to re-run a single stage (e.g. regenerate briefs after a prompt-version bump):

```powershell
# Tag aspects only — Haiku via Anthropic; excludes 'deal' content per default
.venv\Scripts\python scripts/tag.py --run-config configs/run_wave5_v1.yaml --provider anthropic --commit-every 50

# Regenerate one product's brief at the current prompt_version
.venv\Scripts\python scripts/synthesize.py --product-id alienware_16_aurora --run-id run_wave5_v1

# Regenerate every brief at the current prompt_version (skips tagging + aggregation)
.venv\Scripts\python scripts/run_stage_b.py --skip-tagging --skip-aggregation --include-stage-a-briefs
```

---

## View the results

Two serving modes:

| Mode | Command | What it does | When to use |
|---|---|---|---|
| **Unified (recommended)** | `python scripts/serve_public.py` | Builds the SPA into `frontend/dist/` and runs one FastAPI process on `:8765` that serves both `/api/*` and the SPA at every other path. | Demo, public share, the path Tailscale Funnel maps to `/pulse-check`. |
| **Dev (split)** | `python scripts/serve.py` | Vite dev server on `:5173` + FastAPI on `:8000`. Hot reload on the frontend. | Frontend development. |

The webapp lands on the home page with three card surfaces (Standalone / Head-to-head / Heatmap), a one-line run-metadata strip, an expandable Sources accordion, and an expandable "Under the hood" pipeline explainer. Every drill-down opens an Evidence drawer with verbatim quotes pulled from the DB.

### Public deployment via Tailscale Funnel

```powershell
# In one terminal, run the unified server
.venv\Scripts\python scripts/serve_public.py --port 8765

# In another, expose it through Tailscale Funnel under /pulse-check
tailscale funnel --bg --set-path=/pulse-check 8765
```

A frontend or backend change requires re-running `serve_public.py` (the build step picks up frontend edits; uvicorn picks up backend edits via `--reload`). The dev `serve.py` flow is the better fit during active iteration.

---

## Quarterly refresh procedure

The operational cadence is **quarterly** — public-voice drift on PC laptops is months, not weeks, so a quarterly refresh catches every review cycle worth catching without burning operator review time on cosmetic deltas. Estimated steady-state: ~$15–25 per refresh in LLM spend (~$60–100/year) + ~2–3 hours of operator review time per refresh. Monthly cadence multiplies review time for marginal new signal; weekly is mostly noise.

```powershell
# 1. Re-scrape — incremental; cached HTTP responses + dedup on mention_id mean
#    only genuinely new content goes to the LLM in subsequent stages.
.venv\Scripts\python scripts/scrape.py --run-config configs/run_wave5_v1.yaml

# 2. Re-classify any newly-ingested mentions for content type
.venv\Scripts\python scripts/classify_content_type.py --run-config configs/run_wave5_v1.yaml

# 3. Re-run Stage B end-to-end under the same run_id. The LLM cache absorbs
#    every unchanged mention, so the bill scales with delta, not corpus.
.venv\Scripts\python scripts/run_stage_b.py --commit-every 50 --include-stage-a-briefs

# 4. Rebuild the frontend bundle and restart the unified server
.venv\Scripts\python scripts/serve_public.py
```

Briefs from the prior cadence are preserved in the `briefs` table as an audit trail — the `latest_brief_id` lookup picks the newest one for each product, but every older version is still readable via `/api/brief/:id`.

---

## Evaluation

```powershell
# Build a gold set for the aspect-tagging classifier (Sonnet labels + operator
# spot-check). Default sample size = 150 with stratification across products
# and content_type buckets.
.venv\Scripts\python scripts/build_gold_set.py --task aspect_tagging --run-config configs/run_wave5_v1.yaml

# Interactive operator review of the Sonnet labels (accept / correct / flag)
.venv\Scripts\python scripts/review_gold_set.py data/gold_sets/aspect_tagging_v2.jsonl

# Run the production classifier (Haiku) against the gold set; emits per-aspect
# F1 + per-tuple micro-F1 + a JSON report under data/eval_results/
.venv\Scripts\python scripts/run_eval.py
```

The current v1 demo ships at micro-F1 ≈ 0.60 on `aspect_tagging_v2` (Opus-scrubbed) — operator-accepted ship-with-caveat; the real exit criterion is brief quality, with formal F1 ≥ 0.80 reserved for a future labeler-tightening pass. Eval methodology + the brief-quality citation-integrity tests in [`docs/TESTING.md`](docs/TESTING.md).

---

## Project layout

```
pulse-check/
├── pulse_check/             # Python package (config, scraping, storage, tagging,
│                            #   synthesis, aggregation, eval, llm_cache, api)
├── frontend/                # Vite + React + TS + Tailwind + shadcn/ui
├── scripts/                 # CLI entry points (scrape, tag, synthesize, eval,
│                            #   run_stage_a, run_stage_b, serve, serve_public)
├── configs/                 # product-set / pair-plan / run-config YAMLs
├── alembic/                 # schema migrations
├── data/                    # local persistent state (gitignored):
│                            #   pulse_check.db, scrape_cache/, gold_sets/,
│                            #   eval_results/, discovered_urls/
├── tests/                   # unit + integration + eval
├── docs/                    # PRD, ARCHITECTURE, DESIGN_SYSTEM, TESTING,
│                            #   TASKS, SESSION_LOG
├── CLAUDE.md                # Claude project-scoped guidance
├── pyproject.toml
├── alembic.ini
├── .env.example
└── README.md                # this file
```

## Documentation

- [`docs/PRD.md`](docs/PRD.md) — what pulse-check is, audiences, scope, success criteria, non-goals
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data flow, schema, configs, LLM contracts, trade-offs, operator workflow
- [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) — tokens, component conventions, screen inventory
- [`docs/TESTING.md`](docs/TESTING.md) — gold-set methodology, eval harness, citation integrity, test tiers
- [`docs/TASKS.md`](docs/TASKS.md) — wave-by-wave implementation plan
- [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md) — running chronicle; start here when resuming after a break
- [`CLAUDE.md`](CLAUDE.md) — project-scoped guidance for Claude (collaboration protocol, principles)

## License

To be decided at v1 release.
