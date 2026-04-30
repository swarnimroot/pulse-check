# Session log

Running one-page chronicle. Updated **at session close**, when the operator says "wrap up" / "update session log" / similar. Most-recent session at the bottom of the history; **next-session starter prompt at the top** for easy resume.

---

## Next session starter

Paste at the start of your next session:

> Resume pulse-check session 5. Read `CLAUDE.md` + `docs/SESSION_LOG.md`.
>
> **Audit session 4 deliverable (Wave 2 bite 5 — A1 aggregator) before forward work.**
>
> 1. **Regression baseline.** `pytest -q` (expect **180 pass**) · `mypy --strict pulse_check scripts` (expect **38 source files clean**) · `ruff check pulse_check scripts tests` (expect clean). Flag deviations.
> 2. **Code read-through.** Skim `pulse_check/aggregation/a1.py` + `tests/unit/aggregation/test_a1.py`. Flag drift from doctrine: every mention = 1.0; sorted+deduped `mention_ids` provenance; polarity & intensity as separate distributions (zero-filled); PRIMARY-only filter; idempotent rerun via delete-then-insert keyed on `(run_id, product_id)`; caller owns transaction (flush only).
> 3. **Pending operator decision.** Confirm smoke-scrape green-light. (Still open from session 4; first git commit landed at session-4 close — root commit `bfd94d6`.)
>
> After audit:
> - **Smoke scrape green-lit** → **first, pre-flight:** confirm Ollama is reachable (`curl -fsS http://localhost:11434/api/tags`) and `ANTHROPIC_API_KEY` in `.env` is non-placeholder. Surface failures to the operator before launching the pipeline. Then: `python scripts/scrape.py --run-config configs/run_smoke_test.yaml` → `python scripts/tag.py --run-config configs/run_smoke_test.yaml` → `python scripts/build_gold_set.py --task aspect_tagging --run-config configs/run_smoke_test.yaml --total 50` → operator spot-checks via `python scripts/review_gold_set.py data/gold_sets/aspect_tagging_v1.jsonl`. Validates the Wave 2 ≥80% gold-set accuracy gate.
> - **Smoke scrape still gated** → push into Wave 2 bite 6 (synthesis: Haiku dedup + Sonnet verbatim selector + Sonnet A1 brief writer + citation validator), code-only on fixture rows. Note: meaningful testing requires real corpus eventually — pure-fixture bite 6 is possible but limited.

## Current state

- **Phase:** Wave 1 closed. Wave 2 ~50% — tagging pipeline + gold-set machinery + A1 aggregator built and unit-tested. Synthesis + backend handlers + frontend atoms not yet started.
- **Awaiting operator input on:** smoke-scrape green-light. (First git commit landed at session-4 close; repo now under version control at root commit `bfd94d6`.)
- **180 unit tests passing · `mypy --strict` clean on 38 source files · `ruff` clean.**
- **Working code:**
  - **Foundation (session 2):** `pulse_check/` storage + config + llm_cache + scraping + tagging.OllamaClient + synthesis.AnthropicClient; `scripts/scrape.py`; Alembic migration applied to `data/pulse_check.db`; 6 example YAML configs.
  - **Wave 1 shell (session 3, visual confirmed session 4):** `pulse_check/api/main.py` (FastAPI factory + `/health` + `/products`/`/pairs` stubs + CORS + error envelope); full `frontend/` Vite+React+TS+Tailwind v3+shadcn-ready scaffold with DESIGN_SYSTEM §3 tokens; three themed route shells render correctly in browser; `scripts/serve.py` dual-server launcher.
  - **Wave 2 tagging (session 3):** `pulse_check/tagging/aspect_classifier.py` (prompt v1 with 11 aspects + 22 synthetic anchors), `pulse_check/tagging/batch.py` (idempotent corpus tagger), `scripts/tag.py` CLI.
  - **Wave 2 gold set (session 3):** `pulse_check/eval/gold_set.py` (stratified sampling, Sonnet labeling via `call_with_cache`, JSONL IO), `scripts/build_gold_set.py`, `scripts/review_gold_set.py` (interactive operator-spot-check CLI).
  - **Wave 2 aggregation (session 4):** `pulse_check/aggregation/a1.py` (`aggregate_a1` rolls `aspect_tags` → `aggregates_aspect_sku` with sorted+deduped `mention_ids` provenance, zero-filled polarity/intensity distributions, flat `net_sentiment`, `verified_share`, by-source/by-recency splits; PRIMARY-only; idempotent delete-then-insert keyed on `(run_id, product_id)`).
- **Not yet started (Wave 2 remainder):**
  - Bite 6: Haiku dedup + Sonnet verbatim selector + Sonnet A1 brief writer + citation validator
  - Bite 7: Backend `/products`, `/product/:id`, `/mentions?ids=...`, `/brief/:id` real handlers
  - Bite 8: Frontend atoms (`VerbatimCard`, `AggregateNumber`, `EvidenceDrawer`, `BriefPanel`, `AspectRow`)
  - Bite 9: `/product/:id` page wired end-to-end + Wave 2 exit-criteria check
- **Awaiting live data:** Wave 2 exit-criteria gate (≥ 80% gold-set accuracy) and `/product/:id` end-to-end render both require the smoke scrape + Sonnet gold labeling to have run at least once.

## Things to verify when next session resumes

Manual checks the prior session couldn't / didn't do, listed so they don't get lost:

- **Aspect classifier anchors are synthetic** — 22 short verbatims approximating gaming-laptop review language. Will see real Qwen behavior on the first real tagging pass; expect a v2 anchor refinement after eval.
- **Sonnet gold labeling reuses the Qwen prompt verbatim** — same label space (deliberate). If Sonnet labels look weak during operator spot-check, consider a richer Sonnet-specific prompt as a separate bite.
- **No live LLM contact yet anywhere** — all Ollama + Anthropic calls in tests are mocked. The first real Ollama hit happens when `scripts/tag.py` runs; the first real Sonnet hit when `scripts/build_gold_set.py` runs.
- **A1 aggregator on real data** — never run on real corpus. Eight computed fields per row (`total_mentions`, `polarity_counts`, `net_sentiment`, `intensity_counts`, `verified_share`, `by_source`, `by_recency`, `mention_ids`); fixture tests cover each, but real data may surface schema-fit issues (e.g. metadata key variations across scrapers-lib sources for `verified_purchase`).

## Open items to revisit (deferred, not lost)

Carrying forward from session 1:
- **Tombstoning retention policy** — exact retention window + UI badge wording. Defer to implementation.
- **Demo pair plan breadth** — currently all 10 Alienware-vs-competitor pairs; operator may want to narrow to ~5 segment-matched pairs. Easy toggle in pair-plan config.
- **Anchor attribution regex patterns** — refine iteratively during first scrape pass. Live in `configs/product_set_*.yaml` (no code change required; scrapers-lib wrappers auto-prepend `re:` prefix).
- **BestBuy API key** — not blocking for v1; Tier 3 paginated reviews cover the review signal without it.
- **Alienware display font licensing** — fallback chain Eurostile → Exo 2 → Rajdhani in place per DESIGN_SYSTEM §8.3 (Exo 2 + Rajdhani loaded from Google Fonts in `frontend/index.html`); revisit if the brand font becomes licensable.
- **YouTube + article seed lists** — parallel prereq task (curate ~50–75 YouTube URLs + ~150–200 article URLs for the 10-pair demo); needed by Wave 5.

Carrying forward from session 2:
- **ProductSnapshot table (v1.5?)** — scrapers-lib's Amazon product fetcher emits `ProductSnapshot` (price, rating, review_count, specs). v1 ingester skips and counts them. If price tracking becomes in-scope, add a snapshot table + ingest branch.
- **Reddit thread-level fetching** — Wave 3 deliberation decoder needs `fetch_reddit_comments` on individual threads; orchestrator currently only enqueues `fetch_reddit_listing` per subreddit. Wave 3 will add thread-discovery + thread-fetch enqueueing.

Added in session 3:
- **Aspect classifier prompt v2 anchor refresh** — after the first real Qwen pass + eval, expect to refine the 22 synthetic anchors with real-language patterns. Bumping `PROMPT_VERSION = "aspect_classifier_v2"` cold-starts the cache; old `_v1` rows stay as audit trail.
- **Sonnet-specific gold-set prompt** — currently Sonnet uses the Qwen prompt verbatim. Revisit if operator spot-check shows Sonnet labels are weak; richer prompt would live alongside as `aspect_classifier_sonnet_v1`.
- **`scripts/serve.py` Windows job-control** — uses `subprocess.terminate()` which is a soft kill; on Windows this sends Ctrl+Break to console children, not necessarily to grandchildren (npm → node). If serve.py leaves orphaned vite processes, switch to `subprocess.Popen(creationflags=CREATE_NEW_PROCESS_GROUP)` + `os.kill(pid, signal.CTRL_BREAK_EVENT)`. Watch for it next session.
- **`API_ALLOWED_ORIGINS` env parsing footgun** — pydantic-settings parses `list[str]` from env as JSON, so the `.env` value must be `["http://localhost:5173"]` not `http://localhost:5173`. Documented in `.env.example` but easy to mis-edit.
- **Cache key for the classifier excludes display_name** — by design (rename without retag), but means changing only `display_name` in a product config doesn't reflect in cached labels. Acceptable for the rename case; flag if surprising.

Added in session 4:
- **`aggregates_aspect_sku` schema lacks version columns** — uniqueness is `(run_id, product_id, aspect)` only. Re-aggregating against a different `(taxonomy_version, prompt_version)` overwrites prior rows. Acceptable as "current pass" semantics; if version-stratified aggregates are ever needed, add `taxonomy_version` + `prompt_version` columns + extend uniqueness key (Alembic migration). Flagged in-conversation when bite 5 was implemented.
- **Subagent file-creation blocked in this harness** — Write/Bash mkdir denied for background subagents (saved as memory `feedback_subagent_write.md`). Code-writing tasks must run in foreground; use subagents for read-only research only. Watch if permissions change.

---

## Session history (newest first)

### 2026-04-30 — session 4: audit + Wave 2 bite 5 (A1 aggregator)

**Context entering.** PC restart had ended session 3 mid-stride; nothing was lost (work on disk, no git history yet). Mission: run the prescribed audit pass on session 3 deliverables, then progress Wave 2.

**Audit pass.**
- Regression baseline before forward work: `pytest -q` 168 pass · `mypy --strict` clean on 37 files · `ruff` clean. Slight drift from session-3-recorded baseline (163/36) — likely a final tweak landed before session 3 closed without updating SESSION_LOG counts. Healthier than baseline, not regressed.
- Code read-through on `api/main.py`, `tagging/aspect_classifier.py`, `tagging/batch.py`, `eval/gold_set.py` — all doctrine-compliant (temp=0 pinned, cache-key contract honored, display_name correctly excluded from classifier cache key, gold-set sampler PRIMARY-only with seeded RNG).
- Frontend visual confirmed by operator — three routes (`/`, `/product/demo`, `/pair/demo`) render in browser via `python scripts/serve.py`.
- Operator authorized `git init` (done; no first commit yet — operator hasn't asked).

**Bites completed.**

5. **Wave 2 Bite 5 — A1 aggregator.**
   - `pulse_check/aggregation/a1.py`: `BatchAggregateStats` frozen dataclass + `aggregate_a1(session, *, run_id, product_ids, taxonomy_version, prompt_version, now=None)`. Rolls `aspect_tags` into `aggregates_aspect_sku` rows per `(product, aspect)` group. Doctrine: every mention = 1.0; polarity/intensity as separate distributions (zero-filled); `mention_ids` provenance sorted+deduped; PRIMARY attribution only; deterministic ordering for stable tests. Idempotency via delete-then-insert keyed on `(run_id, product_id)` — an aspect that drops to zero on rerun has its prior row removed. `now` is injectable for deterministic recency-bucket tests.
   - `pulse_check/aggregation/__init__.py` re-exports `aggregate_a1` + `BatchAggregateStats`.
   - 12 unit tests in `tests/unit/aggregation/test_a1.py`: happy path · zero-fill polarity/intensity · `net_sentiment` formula · `verified_share` with metadata variations · `by_source` split with multiple SourceTypes · `by_recency` across all 5 buckets including unknown · secondary attributions excluded · out-of-scope products skipped · version scoping · idempotent rerun · empty product set noop · no-matching-tags noop.
   - Final: 168 → **180 tests pass** · mypy clean on 37 → **38 source files** · ruff clean.

**Subagent operational learning (saved as memory).** Spawned the bite-5 work to a background subagent twice; both failed:
- Attempt 1: 10 min / 32 tool uses on file exploration before stream timeout — agent never wrote any code.
- Attempt 2: harness denied every Write + Bash mkdir for the subagent. Agent designed the code but couldn't save. Foreground-write by the parent was the working path.
Saved as `feedback_subagent_write.md` so future sessions don't re-discover.

**Schema design call flagged.** `aggregates_aspect_sku` carries no `taxonomy_version` / `prompt_version` columns — uniqueness is `(run_id, product_id, aspect)`. Re-aggregating against a different prompt version overwrites prior rows. Acceptable for now ("current pass" semantics) but flagged for revisit if version-stratified aggregates are ever needed (Alembic migration to add columns + extend uniqueness key).

**Decision deferred to next session.**
- **Smoke-scrape green-light** still pending. Operator received plain-English walkthrough this session but hasn't authorized.

**Session-close action — first git commit.** Operator authorized at session close. Initial commit (root commit `bfd94d6`) covers all work through session 4: 119 files, 14,664 insertions. `.gitignore` (from session 2) excluded `.env` + `data/` + caches; `.claude/settings.local.json` included (project-local, no secrets). The "first git commit" gate is closed; SESSION_LOG starter and Open Items updated to reflect.

**Artifacts created (session 4).**
- `pulse_check/aggregation/a1.py` (~190 lines)
- Edit to `pulse_check/aggregation/__init__.py` (re-exports)
- `tests/unit/aggregation/__init__.py`
- `tests/unit/aggregation/test_a1.py` (~430 lines, 12 tests)
- Memory: `feedback_subagent_write.md` + MEMORY.md update

**Session closed at Wave 2 ~50%; pending smoke-scrape decision + first git commit.** Operator triggered the close-out citing context budget; next session opens with the audit pass per the standard handoff pattern.

---

### 2026-04-24 — session 3: Wave 1 close + Wave 2 bites 2-4

**Context entering.** Node 20+ LTS installed (v24.15.0 / npm 11.12.1) per session-2 blocker resolution. Mission: close the Wave 1 frontend + backend shell bite, then push into Wave 2. Operator authorized Wave 2 forward motion mid-session ("keep going into wave 2") — Decisions 2-5 from the bite-1 plan answered at the proposed defaults; Decision 1 (real smoke scrape) left as an explicit gate.

**Bites completed (all green on ruff + mypy --strict + pytest, 109 → 163 tests).**

1. **Wave 1 — Frontend + backend shells.**
   - **Backend.** `pulse_check/api/main.py` factory pattern: `create_app()` returns a configured FastAPI with CORS (origins locked to Vite dev), uniform error envelope `{error:{code, message, detail?}}` via generic `Exception` + `HTTPException` handlers, three handlers: `/health` (status + version + UTC timestamp), `/products` + `/pairs` stub envelopes the frontend will code against. Settings extended with `API_HOST`, `API_PORT`, `API_ALLOWED_ORIGINS` (JSON-parsed list); `.env.example` updated.
   - **Frontend.** `frontend/` Vite + React 18 + TypeScript + React Router DOM v6 + Tailwind v3 + shadcn/ui-ready manual scaffold (no `shadcn init` — Windows-friendly + reproducible). Tailwind config wires every DESIGN_SYSTEM §3 token into CSS custom properties in `src/index.css` (surface / text / accent / sentiment / intensity / addressability + shadcn semantic aliases). Three themed route shells at `/`, `/product/:id`, `/pair/:id`, each exercising the dark surface + display font + accent. Inter (body) + Exo 2 + Rajdhani (display fallback chain per §8.3) loaded via Google Fonts in `index.html`. API client `src/lib/api.ts` typed against the stub shapes, reads `VITE_API_URL`. `components.json` + `cn()` utility staged so `npx shadcn@latest add …` works in Wave 2.
   - **`scripts/serve.py`.** Cross-platform dual-server launcher; threads-per-stream prefix `[api]`/`[web]`, resolves `npm.cmd` on Windows, Ctrl+C terminates both children with kill-fallback after 5s. Flags: `--backend-only`, `--frontend-only`, `--backend-port`, `--frontend-port`.
   - **Verification.** `npm run build` (tsc -b + vite build) green in 3.1s. Booted both servers; `/health` returned the expected envelope, stub routes returned the documented shapes, all three frontend routes returned the themed `index.html` with `class="dark"` + Google Fonts links + `#root` mount, and Vite-transformed `main.tsx` resolved React/Router/App/CSS cleanly. **Operator has not yet visually confirmed the rendering in a browser** — flagged as session-4 first task. `scripts/serve.py` itself was not run as a launcher in this session (each server tested independently).
   - 6 new API unit tests (envelope shape, CORS header, 500-path through middleware, HTTPException passthrough).

2. **Wave 2 Bite 2 — Aspect classifier + prompt v1.**
   - `pulse_check/tagging/aspect_classifier.py`: `ProductContext` + `AspectPrediction` dataclasses, `PROMPT_VERSION = "aspect_classifier_v1"`, `TAXONOMY_VERSION = "v0"`, `build_prompt(...)`, `parse_response(...)`, `AspectClassifier(client, model, temperature, prompt_version)` class. The class wraps the existing `OllamaClient.generate_json` + `call_with_cache`. Cache key is `(mention_text, product_id, prompt_version, model, temperature)` — display name is **only** in the prompt text, not the key, so renames don't invalidate the cache.
   - **Prompt v1** embeds the 11 v0 aspects with one-line definitions + 22 synthetic anchor verbatims (2 per aspect, mixed polarity / intensity). The anchor inventory is hand-written and never exposed to a real Qwen call yet — expect a v2 refresh after the first real eval pass.
   - **Parser** is robust-by-default: top-level shape errors raise `LlmParseError`; per-tag malformations (unknown aspect, missing required field, malformed polarity / intensity, out-of-range or boolean confidence) are dropped with a `log.warning` so a single hallucinated label doesn't fail the whole batch. Aspect / polarity / intensity values are case-canonicalized via `.strip().lower()` before enum coercion.
   - 24 new unit tests covering taxonomy + prompt version constants, prompt determinism + per-product variation, every parse_response branch (happy / empty / case-canon / unknown-aspect-drop / missing-field-drop / unknown-polarity-drop / non-dict / missing tags key / tags-not-list / out-of-range confidence / bool confidence), and 6 integration tests against `httpx.MockTransport` + the in-memory SQLite session fixture covering cache miss + hit + per-product scoping + per-text scoping + temperature-zero in request body + prompt_version-bump invalidation.

3. **Wave 2 Bite 3 — Batch tagger + `scripts/tag.py`.**
   - `pulse_check/tagging/batch.py`: `BatchTagStats` + `tag_corpus_aspects(session, *, classifier, products, taxonomy_version)`. Iterates every primary-or-secondary `MentionAttribution` whose `product_id` is in the supplied set, calls `classifier.classify` on each unique `(mention, product)` pair, upserts `AspectTag` rows stamped with `taxonomy_version`, `prompt_version`, `model`, `temperature`. Idempotency via a pre-pass query of existing `aspect_tags` rows under the same `(taxonomy_version, prompt_version)` — pairs already tagged are skipped without invoking the classifier. Pairs that exist but have zero tags reclassify on next pass; the LLM cache makes that a no-op. Primary + secondary attribution to the same `(mention, product)` pair → one classify, one set of tags, second attribution skipped via a transient `already_tagged` set.
   - `scripts/tag.py`: CLI taking `--run-config`, loads run config + product set, builds `ProductContext` list, opens an `OllamaClient` against `OLLAMA_HOST`, runs `tag_corpus_aspects`, logs the `BatchTagStats`.
   - 6 unit tests: happy path with metadata stamping, idempotent rerun, out-of-scope attributions skipped, primary+secondary dedup, empty-products-noop, multi-aspect-per-mention.

4. **Wave 2 Bite 4 — Gold set build + review CLIs.**
   - `pulse_check/eval/gold_set.py`: `SampledAttribution` + `GoldSetEntry` dataclasses; `sample_attributions_stratified(session, *, product_ids, total, rng)` uniformly distributes the budget across the 6 `SourceType` buckets with remainder distributed in source-value alphabetical order; **PRIMARY attributions only** (secondary is A2 territory in Wave 3); seeded RNG for reproducibility. `label_with_sonnet(session, *, samples, client, model)` routes through `call_with_cache` with `prompt_version=ASPECT_PROMPT_VERSION` so re-running is free; reuses the Qwen classifier prompt verbatim so labels sit on exactly the same label space being evaluated. `write_jsonl` / `read_jsonl` round-trip with tolerance for missing optional operator fields.
   - `scripts/build_gold_set.py`: CLI with `--task aspect_tagging --run-config <yaml> [--total 150] [--seed 42] [--out path]`; refuses to start without `ANTHROPIC_API_KEY`; warns if no attributions match (corpus empty). Default output: `data/gold_sets/<task>_v1.jsonl`.
   - `scripts/review_gold_set.py`: interactive operator-review CLI driven by stdin actions: `[a]ccept`, `[f]lag` (with optional note), `[c]orrect` (with JSON labels + note), `[s]kip`, `[q]uit`. Already-reviewed entries (`operator_flag is not None`) skipped automatically so partial reviews resume cleanly. Implementation has an injectable `inp: TextIO` seam → fully unit-testable via `io.StringIO` (10 tests).
   - 14 unit tests on sampling + Sonnet labeling + JSONL IO + 10 unit tests on the review-CLI state transitions.

**Key design decisions (session 3, all flagged in-conversation when made).**
- **Tailwind v3, not v4.** Operator's prompt explicitly named `tailwind.config.ts`. v4 uses CSS-based config; staying on v3 matches the explicit instruction.
- **React Router DOM v6** (`BrowserRouter` + `Routes`); v7 data-mode is overkill for shells.
- **Manual shadcn scaffold** rather than `npx shadcn@latest init` — avoids interactive prompts on Windows; first real component add is `npx shadcn@latest add <name>` with zero further setup.
- **Eurostile font fallback chain** uses Google Fonts (Exo 2, Rajdhani) since Eurostile itself isn't on Google Fonts; matches DESIGN_SYSTEM §8.3 "quietly degrade" posture.
- **CORS allow-list locked to localhost dev origins.** Staging/prod origins land when those exist.
- **Cache key for classifier excludes display_name** — same product renamed shouldn't retag (it's a rename, not a relabel). Operator can bump prompt_version to force retag if needed.
- **Sonnet gold-set reuses Qwen prompt verbatim** — identical label space. Revisit with a Sonnet-specific prompt if spot-check shows weak labels.
- **Sampling stratifies by `source_type`, not by aspect.** Aspect-stratification would require knowing labels in advance (a chicken-and-egg with the eval). Source-stratified avoids the dominant-source problem; rare-aspect under-representation can be fixed by bumping `--total` or adding aspect-targeted oversampling in a later bite.
- **Gold-set sampling is PRIMARY-attribution only.** Secondary attributions are A2's "considered mention" corpus, out of scope for A1 eval.
- **Gold-set JSONL has no header line** — file is a flat array of records; format version lives in the filename suffix (`aspect_tagging_v1.jsonl`).

**Decision deferred to next session.**
- **Smoke-scrape green-light** still pending. Bite 1 of the original Wave 2 plan was "run `scripts/scrape.py` against `configs/run_smoke_test.yaml` to populate the corpus with real Reddit data." Operator has not specifically authorized; the gate stands. Until it lifts, code-only bites can continue (5: aggregator, 6: synthesis, 7: API handlers, 8: frontend atoms) but the Wave 2 exit criterion (≥ 80% gold-set accuracy) cannot be measured.
- **`git init`.** Three sessions of working code, no version control. Pending operator authorization.

**Artifacts created (session 3).**
- Backend: `pulse_check/api/__init__.py` (re-export) + `pulse_check/api/main.py` + `tests/unit/api/__init__.py` + `tests/unit/api/test_app.py` + extension to `pulse_check/settings.py` + extension to `.env.example`.
- Frontend: full `frontend/` tree — `package.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`, `tsconfig{,.app,.node}.json`, `components.json`, `index.html`, `.env.example`, `.env.development`, `.gitignore`, `src/{main,App,index.css,vite-env.d.ts}`, `src/lib/{api,utils}.ts`, `src/pages/{Landing,Product,Pair}.tsx`. 145 npm packages installed.
- `scripts/serve.py` (cross-platform dual-server launcher).
- Tagging: `pulse_check/tagging/aspect_classifier.py` + extension to `pulse_check/tagging/__init__.py` + `pulse_check/tagging/batch.py` + `scripts/tag.py` + `tests/unit/tagging/test_aspect_classifier.py` + `tests/unit/tagging/test_batch.py`.
- Eval: `pulse_check/eval/gold_set.py` + extension to `pulse_check/eval/__init__.py` + `scripts/build_gold_set.py` + `scripts/review_gold_set.py` + `tests/unit/eval/__init__.py` + `tests/unit/eval/test_gold_set.py` + `tests/unit/eval/test_review_cli.py`.
- Memory: `feedback_session_handoff.md` + MEMORY.md updated.

**Session closed at Wave 1 done + Wave 2 ~40% done; pending operator audit + smoke-scrape decision.** No git commits — repo still not under version control. Operator triggered the close-out citing context window depth (267k / 1M tokens used) and explicitly asked the next session to be set up for an audit pass before continuing forward work. Next-session starter prompt above prescribes that audit.

---

### 2026-04-23 — session 2: Wave 1 foundation (~95% done)

**Context entering.** Docs complete (session 1). No code. Goal: execute Wave 1 per `docs/TASKS.md` — Foundation layer that all later waves build on. Single session, methodical, test-first.

**Bites completed (all green on ruff + mypy --strict + pytest):**

1. **Scaffold + Storage** — `.venv` + `pip install -e ".[dev]"` + `pip install -e ../scrapers-lib`. `pyproject.toml` with deps + tooling. `.gitignore`, `.pre-commit-config.yaml`. Package tree under `pulse_check/` per ARCHITECTURE §2. `pulse_check/settings.py` (pydantic-settings, env-driven). `pulse_check/logging_config.py` (rotating file handler). Storage: `enums.py` (9 StrEnums), `models.py` (12 SQLAlchemy 2.0 declarative models covering every table in ARCHITECTURE §3), `session.py` (engine + `session_scope()`), `types.py` (`UtcDateTime` TypeDecorator for SQLite tz round-trip). Alembic: `alembic.ini`, `alembic/env.py` reading `DATABASE_URL` via `get_settings()`, first migration `fa194da18ea1_initial_schema.py` autogenerated and applied. Tests: `tests/unit/storage/test_models.py` — 10 tests covering JSON round-trip, tz round-trip, tombstoning, unique constraints (aspect_tags + mention_attributions), aggregate provenance, brief citation structure, llm_cache.

2. **Config** — `pulse_check/config/models.py` (Pydantic v2: `ProductSet`, `PairPlan`, `RunConfig`, `SourceWindows` + typed per-source subclasses, slug-pattern + length validators matching storage PK lengths, regex compile-check on `AttributionPatterns`, cross-validator for primary != comparator and unique IDs). `pulse_check/config/loader.py` (`load_product_set` / `load_pair_plan` / `load_run_config` / `load_run`, `ConfigError` for all failure modes, relative path resolution). Example configs: `configs/product_set_smoke_test.yaml` + `configs/pair_plan_smoke_test.yaml` + `configs/run_smoke_test.yaml` (real, loadable, 2 products / 1 pair); `configs/product_set_gaming_laptops_2026.yaml` + `configs/pair_plan_alienware_vs_all.yaml` + `configs/run_demo_2026_04.yaml` (Wave 5 demo placeholders, structurally valid, TODO markers for URLs + seeds). Tests: 29 covering slug constraints, duplicate IDs, invalid regex, unknown product refs, missing files, malformed YAML, smoke round-trip, relative path resolution.

3. **LLM infrastructure** — `pulse_check/llm_cache/cache.py`: `call_with_cache(session, *, task, input_payload, prompt_version, model, temperature, compute)` (inversion-of-control via `compute` callable), deterministic `hash_input` + `cache_key` (temperature normalized to 10 decimal places), `LlmResponse` dataclass, error hierarchy (`LlmError` → `LlmConnectionError | LlmResponseError | LlmParseError`). `pulse_check/tagging/ollama.py`: `OllamaClient.generate_json` over `/api/generate` with `format=json`, parse-retry with strictening suffix, DI via `httpx.Client`. `pulse_check/synthesis/anthropic_client.py`: `AnthropicClient.generate_json` wrapping `messages.create`, same retry semantics + error hierarchy, DI via `anthropic.Anthropic` SDK. Tests: 30 — cache key determinism + bump behavior, hit-skips-compute, miss-stores, mocked httpx and Anthropic transport for happy/connection/response/parse paths.

4. **Scrapers-lib integration** — `pulse_check/scraping/converter.py` (`RawMention` → `Mention` + `MentionAttribution`; `(source, source_type)` → our `SourceType` enum mapping table; metadata rollup for source_title / author_id / parent_id / fetched_at / raw). `pulse_check/scraping/anchors.py` (`ProductConfig` → scrapers-lib `Anchor`; all patterns wrapped with `re:` prefix because scrapers-lib's `AttributionRegex` treats tokens as literal by default — caught by a failing test). `pulse_check/scraping/ingester.py` (upsert mentions by `mention_id`, dedup attributions on unique key; handles the multi-anchor case where one `RawMention` per match arrives with identical `mention_id` by upserting the mention and appending attributions). `pulse_check/scraping/attribution.py` (secondary attribution sweep — combined primary+secondary anchor patterns, skip already-primary or already-secondary, idempotent). `pulse_check/scraping/orchestrator.py` (wires scrapers-lib `Scheduler` with result_sink → ingester + commit per batch; `_enqueue_all_sources` enqueues per enabled source, skipping products without the relevant URL with a log line). `scripts/scrape.py` CLI entry. Tests: 34 covering converter mappings + metadata rollup, anchor building (+ empty-primary warn + `re:` prefix verified against real scrapers-lib), ingester upsert + multi-anchor dedup + idempotent re-run + ProductSnapshot skip, secondary pass (new attribution, skip-when-primary, idempotent, multiple matches per mention).

**Collab-protocol refinement (2026-04-23, mid-Wave-1).** Operator flagged that the "deviations from architecture" sections were too technical and creating false friction. New format for every subsequent bite report: split into **Decisions needed** (product-level only; operator engages) and **Technical housekeeping** (plumbing + small trade-offs + doc cleanups; visible for audit trail, no response expected). Saved as feedback memory `feedback_reporting_format.md`.

**Blocker encountered at end of session.** Node.js not installed (checked bash PATH + Windows via PowerShell). Operator installing Node 20+ LTS. Frontend + backend shells bite paused pending Node availability; will resume in the next session once `node --version` resolves.

**Key technical decisions made during Wave 1:**
- **Enum values stored, not names** (via `values_callable=_enum_values` on every SAEnum column). ARCHITECTURE §3 uses value strings ("reddit_post") throughout.
- **`UtcDateTime` TypeDecorator** in `pulse_check/storage/types.py`. SQLite's driver returns naive datetimes from `DateTime(timezone=True)` columns; the decorator reattaches UTC on read. `impl = DateTime(timezone=True)` so DDL is unchanged — Postgres migration needs no schema change.
- **Typed source-window subclasses** in `SourceWindows` (not open dict). Adding a v1.5 source = new Pydantic subclass + field. DB schema unaffected, matching ARCHITECTURE §4.4's intent.
- **`compute` callable IOC** for LLM cache wrapper. Keeps the cache LLM-agnostic; each client (Ollama, Anthropic) exposes its own retry + error handling.
- **All scrapers-lib anchor patterns prefixed with `re:`** at anchor-build time. Our configs store regex; scrapers-lib treats unprefixed tokens as literals. Caught at test time, confirmed against real `attribute_regex_all`.
- **ProductSnapshot entries are skipped with a counter.** No snapshot table in v1 — if price tracking becomes scope, add the table + ingester branch (~30 lines).
- **Orchestrator builds its own Scheduler.** No injection seam — kept the API lean; add a factory-function seam if orchestrator-level tests become valuable.

**Artifacts created (session 2).**
- Python package code: 28 source files under `pulse_check/` + `scripts/scrape.py`
- 6 example YAML configs under `configs/`
- 103 unit tests under `tests/unit/{storage,config,llm_cache,tagging,synthesis,scraping}/`
- Alembic migration `alembic/versions/fa194da18ea1_initial_schema.py`
- `.env` (operator filled in `ANTHROPIC_API_KEY` placeholder)
- `pyproject.toml` + `.gitignore` + `.pre-commit-config.yaml` + `alembic.ini`
- Memory: `feedback_reporting_format.md` + MEMORY.md updated

**Deferred / flagged.** See *Open items to revisit* above.

**Session closed at Wave 1 ~95%; Frontend + backend shells bite is the only remaining Wave 1 work.** No git commits — operator hasn't asked for `git init` yet; flag on next resume.

---

### 2026-04-23 — session 1: brainstorm + full doc set

**Context entering.** Operator returning to the scrapers-lib ecosystem. Previous consumer-project attempt failed from scope explosion / too many outputs / no clear aha. Goal for this session: design and fully document `pulse-check` as a focused, defensible consumer pilot **before any code is written**.

**What got done.**

- Evaluated pilot shapes PS-1 through PS-6. Operator rejected PS-4 (requires rolling price history we don't have), PS-5 (rare press-vs-buyer contradictions, too thin an aha), PS-6 (monitor posture requires rolling data to start producing value).
- Narrowed to PS-2-flavored ("Deliberation Outcome Decoder") with a focused PS-1 layer.
- Reframed from single-shape pilot to **two-aspect project**:
    - **A1 — standalone product voice** (per-SKU scorecard)
    - **A2 — comparative deliberation decoder** (per-pair win-rate + reasons + addressability)
- Established **product-agnostic** engine framing — products as runtime config, not baked into code.
- Locked **UI stack:** FastAPI + Vite + React + TypeScript + Tailwind + shadcn/ui.
- Locked **storage:** SQLAlchemy ORM + SQLite (v1) + Alembic migrations (Postgres-ready for future cloud migration via connection-string change).
- Locked **LLM routing:** Qwen 7B local for high-volume classification + Sonnet for synthesis/briefs/gold-set-labeling + Haiku for near-duplicate dedup. **No Opus.**
- Established **evidence-first principle** as a core project value: every UI claim traceable to contributing mentions; verbatim text rendered from DB, never from LLM output; Sonnet briefs carry mention-ID citations; deleted upstream content tombstoned locally.
- Established **no-hidden-weighting corollary** — every mention = 1.0 in sentiment aggregates; intensity, verified-status, ownership_duration, engagement, and source type are surfaced *alongside* aggregates rather than folded into a single weighted score.
- Added **polarity + intensity dimensions** per mention-aspect tag (was polarity-only). Classifier gains an intensity field; gold-set labeling covers both; UI surfaces intensity distributions.
- Added **tombstoning** for upstream-deleted content — retain locally, surface with UI badge.
- Adopted **Sonnet-labeled gold set + operator spot-check** eval methodology — ~20–30 min spot-check per prompt version, instead of 2–3 hours of hand-labeling.
- Chose **7-product gaming-laptop demo set** for v1 validation: Alienware 16 Aurora + Alienware 16x Aurora + ROG Strix G16 + ROG TUF 16 + Legion 5 Pro + Legion 7i + HP Omen 16. 10 pairs by default (2 × 5 Alienware-vs-competitor).
- Defined **11-aspect taxonomy v0:** thermals, performance, keyboard, display, battery, build quality, software experience, price-value, support/warranty, aesthetics, portability.
- **Drafted full doc set:** PRD, ARCHITECTURE (13 sections), DESIGN_SYSTEM, TESTING, TASKS, CLAUDE.md, SESSION_LOG, README, `.env.example`.

**Key locked decisions (mirrored in docs).**

- Correctness > speed → v1 timeline ~7–8 weeks.
- Both aspects required for v1; A1-only is an acceptable fallback ship if A2 slips.
- Unified scrape corpus; pair plan pre-computed into saved aggregates; UI toggles between saved pairs.
- No LLM at UI time; all synthesis precomputed.
- No PDF/markdown export (webapp only); desktop only; single-operator auth-less v1.
- Data lives under `data/` (gitignored); `DATABASE_URL` env var for location.
- Alienware brand aesthetic from Pompeii output; font-fallback chain for proprietary display font.

**Artifacts created.**

- All 9 docs above.
- Memory files in `~/.claude/projects/<pulse-check>/memory/`: `user_role.md`, `user_env.md`, `feedback_pilot_focus.md`, `project_pulse_check_v1.md`, `MEMORY.md`.

**Deferred / flagged.**

See *Open items to revisit* above.

**Session closed with full doc set complete and ready to begin Wave 1.** No code written; no git commits. Next session: Wave 1 Foundation.
