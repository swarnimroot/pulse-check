# pulse-check

**Status:** planning &nbsp;·&nbsp; **v1 target:** 2026-Q2

A product-listening pilot engine for PC manufacturers. Takes a configured set of products, pulls public commentary about each (Reddit, retailer reviews, YouTube, gaming press), and produces a webapp with two focused views:

- **Standalone voice** — per-product aspect scorecard showing what buyers and reviewers consistently praise or complain about.
- **Comparative deliberation** — per-pair decoder showing why public deliberators choose one product over the other, classified by whether the reason is messaging-, software-, hardware-, or pricing-addressable.

Product-agnostic engine. Alienware gaming laptops are the first demo; the same engine runs any product set through the same analysis.

---

## What it does

- **Fetches** public commentary via [`scrapers-lib`](../scrapers-lib) across Reddit, BestBuy paginated reviews, Amazon PDP reviews, YouTube transcripts, and gaming-news articles.
- **Attributes** every mention to one or more products via configurable regex patterns.
- **Tags** each mention for aspects (thermals, performance, keyboard, display, battery, etc.) with polarity (neg/neutral/pos) and intensity (low/medium/high) via a local LLM (Qwen 7B on Ollama).
- **Classifies** deliberation threads on Reddit for their resolved outcome + reasoning, for comparative analysis.
- **Synthesizes** scorecards and pair-level briefs with Anthropic Sonnet, under a strict citation contract — every claim resolves to specific mention IDs.
- **Renders** a webapp where every number drills down to its evidence; every verbatim carries its source URL + metadata.

## What it doesn't do

See [`docs/PRD.md` §4.2 Non-goals](docs/PRD.md). Highlights:

- Not a consumer-facing buying tool.
- Not a real-time monitoring dashboard (v1 runs analyses on demand).
- Not a general brand-sentiment tool; every analysis is product-set-scoped.
- No PDF/markdown export, no mobile, no multi-user auth.

---

## Prerequisites

- **Python 3.12**, git-bash or PowerShell on Windows
- **[Ollama](https://ollama.com)** running locally + `qwen2.5:7b-q4_K_M` (or equivalent Qwen 7B) pulled
- **[Anthropic API key](https://console.anthropic.com)**
- **[scrapers-lib](../scrapers-lib)** installed editable in the same Python environment
- **Node.js 20+** + `pnpm` (or `npm`) for the frontend

Hardware baseline: 8GB+ VRAM GPU (RTX 5070 / 12GB confirmed comfortable), 16GB+ RAM. Qwen 7B Q4_K_M runs at ~60–120 tok/s on the confirmed setup. CPU-only is possible but slow; not the default path.

## Install

```bash
# From this project directory
python -m venv .venv
source .venv/bin/activate          # or .venv\Scripts\activate on Windows PowerShell

# Install pulse-check (editable) + scrapers-lib (editable from sibling dir)
pip install -e .
pip install -e ../scrapers-lib
playwright install chromium        # for scrapers-lib Tier 2/3 sources

# Frontend
cd frontend && pnpm install && cd ..

# Env
cp .env.example .env               # then edit with your Anthropic key

# Database
alembic upgrade head
```

---

## Run a pilot

```bash
# 1. Configure — edit a run config (or start from the smoke test)
cp configs/run_smoke.yaml configs/my_run.yaml
# edit configs/my_run.yaml to point at your product_set + pair_plan + source windows

# 2. Scrape — patient overnight run
scripts/scrape.py --run-config configs/my_run.yaml

# 3. Tag — LOCAL LLM batch (Qwen); overnight for large corpora
scripts/tag.py --run-config configs/my_run.yaml

# 4. Aggregate + synthesize — Sonnet briefs + addressability
scripts/aggregate.py  --run-config configs/my_run.yaml
scripts/synthesize.py --run-config configs/my_run.yaml

# 5. Serve — backend + frontend dev servers
scripts/serve.py
# Open http://localhost:5173
```

Re-running with the same config hits the LLM cache and scrape cache; outputs are byte-identical.

---

## Evaluation

```bash
# Build a gold set for a classifier (Sonnet labels + operator spot-check)
scripts/build-gold-set.py --task aspect_tagging --sample-size 150

# Review Sonnet labels interactively (20–30 samples, ~15 min)
scripts/review-gold-set.py data/gold_sets/aspect_tagging_v1.json

# Run classifier eval against gold set
scripts/run-eval.py --task aspect_tagging
```

Accuracy thresholds and the full eval methodology: [`docs/TESTING.md`](docs/TESTING.md).

---

## Project layout

```
pulse-check/
├── pulse_check/             # Python package (config, scraping, storage, tagging,
│                            #   synthesis, aggregation, eval, llm_cache, api)
├── frontend/                # Vite + React + TS + Tailwind + shadcn/ui
├── scripts/                 # CLI entry points
├── configs/                 # product-set / pair-plan / run-config YAMLs
├── alembic/                 # schema migrations
├── data/                    # local persistent state (gitignored):
│                            #   pulse_check.db, scrape_cache/, gold_sets/, etc.
├── tests/                   # unit + integration + eval
├── docs/                    # PRD, ARCHITECTURE, DESIGN_SYSTEM, TESTING, TASKS,
│                            #   SESSION_LOG
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
- [`docs/TASKS.md`](docs/TASKS.md) — wave-by-wave implementation plan with A1 cutpoint
- [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md) — running chronicle; start here when resuming after a break
- [`CLAUDE.md`](CLAUDE.md) — project-scoped guidance for Claude (collaboration protocol, principles)

## License

To be decided at v1 release.
