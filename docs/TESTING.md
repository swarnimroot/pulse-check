# pulse-check — Testing

**Status:** draft &nbsp;·&nbsp; **Paired docs:** [`PRD.md`](PRD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md)

This document covers how pulse-check is tested. Correctness is the explicit top priority (PRD §10); testing is first-class, not a closing-wave afterthought. Four tiers: unit, integration, **LLM eval**, and **citation integrity** (unique to evidence-first).

---

## 1. Testing philosophy

- **Tests run locally, not in CI for v1.** Single-operator project; pre-commit hooks catch lint + type errors; full suite is run by the operator before closing a wave or accepting a significant change.
- **All tests are deterministic where possible.** LLM non-determinism is controlled by `temperature=0` + the `llm_cache` — tests hit the cache or stub the LLM client rather than making live calls.
- **Separation of concerns.**
    - `tests/unit/` — fast, offline, no I/O except filesystem and in-memory SQLite. Target: <30s full run.
    - `tests/integration/` — real SQLite file, scrapers-lib integration with fixture HTML/JSON (no live scraping), orchestration end-to-end on tiny product set. Target: <2 min.
    - `tests/eval/` — runs Qwen against stored gold sets; requires Ollama running locally. Not automatic; run manually before wave close.
- **Every class of bug gets a test at the layer it was introduced.** Bug in the aggregation arithmetic → unit test in `tests/unit/aggregation/`. Bug in citation validation → test in `tests/eval/citation_integrity/`. No drive-by test additions outside the layer.

---

## 2. Tooling

- **pytest** — runner; `pytest-asyncio` if needed for async route tests
- **pytest-cov** — coverage reporting (target ≥ 85% line coverage on `pulse_check/` non-UI code)
- **mypy --strict** — type checking; every module must pass strict
- **ruff** — lint + format
- **pre-commit** — enforces mypy + ruff + a fast unit subset on every commit
- **hypothesis** — property-based tests for attribution regex + aggregation invariants (optional, recommended for attribution edge cases)

Frontend:
- **vitest** — unit tests for React components + TS utilities
- **@testing-library/react** — component behavior tests
- No Playwright / e2e for v1 (manual smoke tests suffice)

---

## 3. Unit tests (`tests/unit/`)

Fast, isolated, offline. One module per production module.

Coverage priorities (highest value first):

- **`tests/unit/config/`** — Pydantic model validation. Malformed YAML, missing fields, invalid regex patterns, unknown product_ids referenced by pair_plan. Ensures the run aborts with a clear message on bad config, never proceeds with silently-wrong state.
- **`tests/unit/attribution/`** — regex matching on known + edge-case mention text. Include: alias variants ("Area-51", "Area 51", "A51", "Area-51 18"), competitor-adjacent mentions ("I considered the Strix"), false-positive traps ("alien-ware" is not Alienware, etc.). Property-based with hypothesis for robustness.
- **`tests/unit/aggregation/`** — given a known set of mention + tag rows, aggregation produces known aggregate rows. Invariants: sum of polarity_counts == total_mentions; mention_ids on an aggregate == the mentions contributing to it (provenance integrity); re-running produces identical output.
- **`tests/unit/storage/`** — SQLAlchemy models, constraint enforcement (unique taxonomy_version on aspect_tags, FK cascades, timezone-aware datetime round-trip on SQLite + Postgres dialects).
- **`tests/unit/llm_cache/`** — key construction, hit/miss, prompt_version bump produces new rows without evicting old, no silent key collisions.
- **`tests/unit/tagging/prompts/`** — snapshot tests on prompt strings (so no silent prompt drift between wave merges). Each prompt carries a `PROMPT_VERSION` constant; snapshot compares against a committed reference.
- **`tests/unit/synthesis/citation_parser/`** — Sonnet's structured output parsed correctly; malformed outputs raise typed errors the caller can handle.

Mocking strategy: LLM clients are mocked with `unittest.mock` in unit tests. Real calls happen only in eval tests.

---

## 4. Integration tests (`tests/integration/`)

End-to-end on a miniature run. Validates that modules compose correctly.

- **Fixture product set:** 2 products (1 primary, 1 comparator), tiny aliased patterns.
- **Fixture corpus:** 30–60 hand-crafted mentions covering all 6 source types, committed as JSON fixtures under `tests/integration/fixtures/`.
- **Scrapers-lib integration test:** stubs the library's HTTP layer (via `respx` or scrapers-lib's own test helpers) to return the fixture payload, verifies that our wrappers convert library outputs to `Mention` rows correctly.
- **Pipeline integration test:** `tests/integration/test_stage_b_pipeline.py` (session 37, extended sessions 38 + 42; 4 tests) seeds a small post-classifier corpus (1 product, 6 mentions with attributions + aspect tags) and runs `aggregate_a1 → synthesize_a1` end-to-end. Stubs `cluster_near_duplicates` + `write_a1_brief` + `write_pair_brief` via monkeypatch so no LLM calls fire. Tests: `test_aggregate_then_synthesize_persists_valid_brief` (aggregate row shape + sentiment arithmetic + Brief schema + persistence + citation-validator pass-through), `test_synthesize_retries_brief_on_fabricated_citation` (retry-with-strict branch fires on fabricated IDs and persists under `a1_brief_v3_strict` constants), `test_aggregate_excludes_tombstoned_mentions` (session 38; tombstones m1 + m2 and asserts the aggregator drops them: total_mentions 6 → 4, polarity_counts neg 4 → 2, mention_ids excludes the tombstoned set), `test_synthesize_pair_persists_brief_with_contrast` (session 42; seeds a 2-product corpus, exercises `synthesize_pair`, asserts the Brief row carries `scope_type=ASPECT_2_PAIR`, `scope_id={primary}_vs_{comparator}`, and the persisted narrative carries the contrast paragraph + cited mention IDs). The fuller `scrape → attribute → tag` end-to-end seam (pre-classifier) remains a future bite.
- **FastAPI integration test:** spins up the app in-process, hits routes, asserts response shapes match the frontend's expected data model.

Integration tests use a real SQLite file in `tests/integration/.tmp/test.db`, migrated fresh per test via Alembic, torn down after.

---

## 5. LLM evaluation — gold-set methodology (`tests/eval/`)

This is where the correctness discipline lands for classification quality. Live LLM calls, gold-set regression, accuracy thresholds.

### 5.1 Gold sets — what they are

A **gold set** is a JSON file in `data/gold_sets/<task>_<version>.json` with ~100–200 mentions, each with human-verified correct labels. Example shape for `aspect_tagging`:

```json
{
  "task": "aspect_tagging",
  "version": "v1",
  "taxonomy_version": "v0",
  "labeled_at": "2026-04-25",
  "labeled_by": "sonnet-4-6 + operator spot-check",
  "spot_check_count": 25,
  "mentions": [
    {
      "mention_id": "m_abc123",
      "raw_text": "...",
      "expected_tags": [
        {"aspect": "thermals", "polarity": "negative", "intensity": "high"},
        {"aspect": "performance", "polarity": "neutral", "intensity": "low"}
      ]
    }
  ]
}
```

Gold sets are committed to the repo only if small enough (~100 mentions, maybe 50KB). Larger sets live in `data/gold_sets/` (gitignored) and are rebuildable on demand via the builder script.

### 5.2 Gold-set builder — the hybrid workflow

Replaces manual hand-labeling of hundreds of mentions with a ~30-minute operator spot-check.

**Steps:**

1. Operator runs `scripts/build-gold-set.py --task aspect_tagging --sample-size 150 --output data/gold_sets/aspect_tagging_v1.json`.
2. Script samples N real mentions from the corpus (stratified — ensures source-type + recency + polarity-variety is represented).
3. **Sonnet labels each mention** via `synthesis.build_aspect_gold_set()` with a careful prompt that lays out the taxonomy + anchor examples + expected JSON schema.
4. Script writes the labeled JSON.
5. Operator opens a helper script (`scripts/review-gold-set.py data/gold_sets/aspect_tagging_v1.json`) that renders each labeled mention one at a time with the Sonnet labels + keyboard shortcuts to **accept / flag / correct**.
6. Operator spot-checks ~20–30 stratified samples (10–15 min of work).
7. If flag rate is low (<10%): accept the Sonnet labels as the gold set. Rare corrections are applied inline.
8. If flag rate is high (>15%): the taxonomy / Sonnet prompt has a systematic issue. Either fix the prompt + rebuild, or fix the taxonomy anchor examples. Don't accept.
9. Accepted gold set saved with `labeled_by: "sonnet-4-6 + operator spot-check"` + `spot_check_count` recorded in the file.

**Why this works:** measuring Qwen against Sonnet alone measures agreement, not accuracy. The spot-check catches systematic Sonnet errors (shared taxonomy blind spots, sarcasm misreads on Reddit, etc.) before the gold set is accepted. Once the spot-check is clean, the broader Sonnet-labeled set is a reasonable ground truth for Qwen.

### 5.3 Gold sets per classifier task

| Task | Gold set filename | Target size | Threshold |
|---|---|---|---|
| Aspect + polarity + intensity | `aspect_tagging_v2.jsonl` | 115 (shipped) / 150 (target) | ≥ 80% **loose micro-F1** (off-by-one intensity-bucket tolerance via `compute_micro_f1_loose`; strict micro-F1 reported alongside but not the gate) |
| Deliberation thread classification | `deliberation_v1.json` | 100 | ≥ 85% binary (is_deliberation + is_resolved) |
| Outcome extraction | `outcome_v1.json` | 100 resolved threads | ≥ 85% exact product match |
| Reason tagging | `reason_tagging_v1.json` | 150 comments | ≥ 80% reason_bucket; ≥ 80% intensity |

**Intensity threshold applies per task** where intensity is emitted (aspect + reason). Measured independently from polarity/bucket accuracy.

### 5.4 Regression test flow

```bash
# Run the full eval suite (takes ~30-60 min depending on corpus size)
scripts/run-eval.py --against-all

# Run one task
scripts/run-eval.py --task aspect_tagging --gold-set data/gold_sets/aspect_tagging_v1.json
```

Output: per-task accuracy + per-dimension breakdown + confusion matrix for classification tasks. If any task is below threshold, the script exits nonzero. Pre-merge rule: never merge a prompt change that regresses below threshold on an existing gold set.

Special case: a prompt change that *improves* accuracy is accepted even if it changes which rows are correct/incorrect — but the aggregate score must not regress.

### 5.5 When to rebuild a gold set

- Taxonomy version bumped (new aspect added, existing aspect split/merged) → rebuild affected gold sets
- Classifier prompt has a structural change (new anchor examples, new output field) → existing gold set stays valid; new accuracy measured against it
- Corpus shifts substantially (e.g., new source type added) → consider re-sampling so the gold set still represents the corpus

---

## 6. Citation integrity tests — evidence-first enforcement

Unique to pulse-check: Sonnet briefs carry mention-ID citations, and those citations must be valid. The test layer validates this on every brief.

### 6.1 What's validated

For each `briefs.narrative` JSON structure:

1. **Every cited mention_id resolves to a real row** in the `mentions` table. Fabricated IDs fail the test.
2. **Cited mentions were in Sonnet's input context** for that brief. Cross-brief ID leakage fails (would indicate Sonnet is hallucinating from training data).
3. **Numerical claims** in narrative text (e.g., "in 60 threads") match the underlying aggregate's count. Regex-extract claim numbers from `claim_text`, cross-reference against the cited aggregate row's `mention_ids` length. Off-by-more-than-5% fails.
4. **No empty citations** — every `claim` object must have ≥ 1 `cited_mention_ids` entry. A claim with no evidence fails.

### 6.2 Where this runs

- As a **post-generation hook** in the `synthesis` module — fails the brief generation with a retry (up to 2 attempts with a stricter prompt appended). If retries exhaust, the brief is written with a flag and the operator is notified.
- As an **integration test** in `tests/integration/synthesis/` — runs a brief generation end-to-end on fixture data, asserts all four validations pass.
- As a **regression test** in `tests/eval/citation_integrity/` — runs against a known-good fixture brief + known-corrupted fixture briefs (hallucinated IDs, off-count claims) and asserts the validator catches them.

Without these tests, evidence-first is aspirational. With them, it's enforced.

---

## 7. Frontend tests (`frontend/src/**/*.test.{ts,tsx}`)

**Stack** — Vitest + `@testing-library/react` + `@testing-library/jest-dom` on jsdom. Co-located test files next to source (no separate `__tests__/` directory). Setup file at `src/test-setup.ts` registers jest-dom matchers and auto-cleans the DOM between tests. Config lives in `vite.config.ts` under the `test` block, using `defineConfig` from `vitest/config` so the `test` field type-checks.

**Commands** — `npm test` (watch mode) and `npm run test:run` (one-shot; current 21 tests run in ~1.2s).

**Current coverage (session 42):**

- `src/lib/exportMarkdown.test.ts` — 5 tests on the pure `briefToMarkdown` function: H1 + brand/window/run-id header, 11-aspect canonical-order table with em-dash fallbacks for no-data rows, `[n, m]` citation refs from caller-provided number map, empty-strengths and empty-complaints fallback strings, Citations section toggles on `citedIds.length > 0`.
- `src/components/WelcomeModal.test.tsx` — 8 tests on the welcome modal: renders on `open=true`, returns null on `open=false`, X button calls `onClose`, Got-it button calls `onClose`, Escape keydown calls `onClose`, backdrop click calls `onClose`, inner-content click does NOT (stopPropagation boundary), all three section eyebrows + 4 use-case row bodies present in DOM.
- `src/components/BriefPanel.test.tsx` — 4 tests on the A1 summary block (session 41): renders summary paragraph when `narrative.summary` present, hidden when null, cite-chip click invokes `onCite` with cited mention IDs, strengths/weaknesses sections unchanged when summary is null.
- `src/components/PairBriefPanel.test.tsx` — 4 tests on the pair-brief contrast paragraph (session 42): renders title + contrast, cite-chip click invokes `onCite` with contrast text + mention IDs, no cite chip when `cited_mention_ids` is empty (placeholder branch), model + prompt_version surface in header.

**Mocking strategy** — pure functions tested with hand-built fixture inputs (typed against the same `@/lib/types` shapes as production). Component tests use `fireEvent` from RTL for click/keydown synthetic events; `vi.fn()` for `onClose` spies. No API-call / network tests in scope yet — `fetch` paths remain stubbed via the data-loader contracts and are exercised by manual operator review, not unit tests.

**No visual regression / screenshot tests** for v1 — manual operator review during wave-close suffices.

---

## 8. What's explicitly not tested

- **Live scraping.** scrapers-lib has its own integration test suite; pulse-check trusts the library and tests at the wrapper boundary.
- **LLM model correctness on unseen data in production.** The gold set is a fixed benchmark; drift on fresh corpora is addressed by periodic gold-set refresh + spot-checks, not automated tests.
- **UI pixel accuracy.** Design system tokens are tested via config presence; visual fidelity is manually verified at wave close.
- **Performance/load testing.** Single-operator desktop app; not a v1 concern.

---

## 9. Test data policy

- **Fixture corpora** (`tests/**/fixtures/`) are committed to the repo. Small, curated, intentionally diverse. Include real-ish text (public Reddit threads, public reviews) — no PII beyond public handles.
- **Gold sets** — small ones (<500 mentions) committed; large ones in `data/gold_sets/` (gitignored), rebuildable.
- **LLM cache fixtures** (`tests/**/fixtures/llm_cache/`) — pre-seeded cache entries keyed on fixture content hashes, so integration tests hit cache and never call live LLMs.
- **Snapshot tests** (`tests/unit/tagging/prompts/`) — committed snapshot files; updated explicitly by running `pytest --snapshot-update` during prompt-version bumps.

---

## 10. Pre-commit, pre-wave, pre-merge gates

| Gate | Runs | Fails on |
|---|---|---|
| **pre-commit hook** | unit tests (fast subset), ruff, mypy --strict | any failure |
| **pre-wave close** | full unit + integration suite | any failure |
| **pre-eval-threshold-merge** | relevant eval task run | below threshold |
| **pre-release (demo run prep)** | full unit + integration + full eval + citation integrity | any failure |

No CI service in v1. The operator runs these locally; pre-commit handles day-to-day hygiene automatically.
