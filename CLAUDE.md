# CLAUDE.md — pulse-check

Project-scoped guidance. Global `~/.claude/CLAUDE.md` still applies; this is additive.

## What this is

Product-listening pilot engine for PC manufacturers. Two aspects: A1 standalone product voice, A2 comparative deliberation decoder. Sits on `scrapers-lib` (sibling, v1.1.0, stable). Full details in [`docs/PRD.md`](docs/PRD.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Non-negotiable principles

- **Evidence-first.** Every UI claim traceable to mention-ID provenance. Verbatim text rendered from DB, never LLM output. Sonnet briefs cite real mention IDs. **No hidden weighting formulas** — every mention = 1.0 in aggregates; intensity / verified / recency / source shown alongside.
- **Correctness > speed.** pytest + mypy + ruff + pre-commit from day 1. All schema changes via Alembic. No timeline shortcuts.
- **Product-agnostic.** No hard-coded product references in code; everything in `configs/` YAML.
- **Deterministic LLM calls.** `temperature=0`, structured JSON output, versioned prompts, cached by `(content_hash, prompt_version, model, temperature)`.
- **No LLM at UI time.** All synthesis precomputed; UI reads SQLite via FastAPI.

## LLM routing

Locked per [ARCHITECTURE §6](docs/ARCHITECTURE.md). Qwen 7B local for volume; Sonnet for synthesis + gold-set labeling; Haiku for near-duplicate dedup; **no Opus**. Per-task fallback to Haiku allowed if Qwen 7B misses a gold-set threshold on a specific classifier. Don't deviate without in-conversation discussion.

## Doc evolution — collaboration protocol

Operator is non-technical on implementation-level detail. Architecture docs are starting skeletons; small deviations during build are expected.

1. When an implementation choice deviates from PRD / ARCHITECTURE / DESIGN_SYSTEM / TESTING / TASKS, **Claude flags the deviation in plain English in-conversation**, explains the reason, waits for operator approval.
2. Once approved, Claude **updates the relevant doc** before moving on. Docs are the source of truth.
3. Claude never silently changes behavior that contradicts docs.
4. Operator may skip technical doc sections (schema, LLM signatures, aggregation arithmetic) and trust the skeleton; plain-English sections (non-goals, workflow, definitional defaults, trade-offs) are where non-technical review matters.

## Session continuity

[`docs/SESSION_LOG.md`](docs/SESSION_LOG.md) is the running chronicle.

- **Update at session close**, not every turn. Operator triggers with "wrap up" / "update session log" / similar.
- **Suggest updating** if a session feels like it's approaching natural close without trigger: one-line ask — "Want me to update SESSION_LOG before we stop?"
- **Read it first at session start** — fastest path to "where were we?"

## Data

All persistent state under `data/` (gitignored). Layout in [ARCHITECTURE §2](docs/ARCHITECTURE.md). `DATABASE_URL` env var for backend (SQLite default; Postgres for future cloud via connection-string change).

## UI posture

Desktop-only, dark-mode-first, Alienware aesthetic, shadcn/ui components on Tailwind, exec-clarity over analyst-depth. Full tokens and components in [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) *(pending draft)*.

## Where to look when in doubt

- **Resume context after a break** → [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md)
- Scope, audiences, success criteria, non-goals → [`docs/PRD.md`](docs/PRD.md)
- Data flow, schema, configs, LLM contracts, trade-offs, operator workflow → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- UI tokens, components, screen inventory → [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) *(pending)*
- Eval methodology, regression tests, citation-integrity tests → [`docs/TESTING.md`](docs/TESTING.md) *(pending)*
- Wave plan with A1 cutpoint → [`docs/TASKS.md`](docs/TASKS.md) *(pending)*
- Setup, prereqs, running a pilot → [`README.md`](README.md) *(pending)*
- scrapers-lib reference → `../scrapers-lib/docs/`
