# Session log

Running one-page chronicle. Updated **at session close**, when the operator says "wrap up" / "update session log" / similar. Most-recent session at the bottom of the history; **next-session starter prompt at the top** for easy resume.

---

## Next session starter

Paste at the start of your next session:

> Resume pulse-check session 12. Read `CLAUDE.md` + `docs/SESSION_LOG.md`. Audit session 11 first per the "Audit checklist (session 11 → 12)" below — verify regression baselines + read the new synthesis keystones — before touching forward work. Then surface the bite pick from "Current state" with reasoning and wait for my call before code. Be very concise. Ultrathink. Use agents for read-heavy work.

### Audit checklist (session 11 → 12)

- Use `.venv/Scripts/python.exe` for tooling — only working Python interpreter on this machine (global `python` lacks `pydantic-settings`/`mypy`/`ruff`).
- `pytest tests/unit/` → confirm **264 pass** (was 246; +18 from selector + brief_writer tests).
- `mypy pulse_check/` → confirm clean on **40 source files** (no count change — selector + brief_writer replaced existing skeletons).
- `ruff check pulse_check/ tests/` → confirm clean.
- Read `pulse_check/synthesis/selector.py` + `pulse_check/synthesis/brief_writer.py` end-to-end (10.4 builds on both).
- Spot-check `docs/ARCHITECTURE.md` §6.3 "A1 brief layout" — the four-quadrant lock 10.4's validator must mirror.
- Confirm `Claim.cited_mention_ids` `min_length=0` relaxation in `pulse_check/synthesis/contracts.py` (placeholder support).

## Current state

- **Phase:** Wave 2 ~85%. Session 9 shipped Option 3 (PRIMARY/SECONDARY dual-track aggregates). Session 10 added synthesis skeleton + §6.3 contracts (10.1) + Haiku dedup (10.2). **Session 11 added the deterministic verbatim selector + Sonnet brief writer (bite 10.3)** — the §6.3 four-quadrant A1 brief layout is operator-locked in ARCHITECTURE.md. Two pipeline modules remain skeletons (citation_validator, orchestrator) — bite 10.4 fills them and unblocks the first real Haiku+Sonnet smoke. Operator decisions still in force from session 10 (brief schema is §6.3; validator is soft-warn) plus session 11 four-quadrant locks (see §6.3).
- **Bite candidates for session 12** (operator picks):
  - **Bite 10.4 — citation validator + orchestrator + CLI.** Soft-warn validator (4 checks per TESTING §6) + retry loop + `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI. After this lands, the full A1 pipeline is ready for the first real Haiku+Sonnet smoke on the 71-mention PRIMARY pool. Estimated ~2h.
  - **Bite 6.3 — YouTube** end-to-end. Operator URL curation + first run; budget plumbing surprises.
  - **Bite 6.4 (still deferred) — retailer reviews.** Three open items unchanged.
  - **Backend/frontend Wave 2 finish.** `/products`/`/product/:id`/`/mentions`/`/brief` real handlers + frontend atoms + `/product/:id` page. Operator has a claude.ai/design prototype to mimic exactly for the BriefPanel/scorecard view — to be shared when frontend bite starts.
- **pulse-check: 264 unit tests passing · `mypy` clean on 40 source files · `ruff` clean.** (Was 246 / 40 at session-10 close; +18 tests from `test_selector.py` (9) + `test_brief_writer.py` (9); mypy file count unchanged because selector + brief_writer replaced existing skeletons.)
- **scrapers-lib: 904 unit tests passing · 20 skipped · ruff clean on edited files.** Drift +60/+1 vs the older 844/19 baseline — flagged in session 9 audit; non-blocking (all green). `_version.py` is **`1.2.1` in HEAD with no working-tree diff** — the deferred-bump open item from sessions 7/8 is **resolved** (already committed; not by us).
- **Capability + output aha both demonstrated for A1.** Session 8 unlocked density (33→1143 mentions); session 9 unlocks output aha (PRIMARY/SECONDARY divergence visible at the aggregate layer). Brief regenerated successfully with sidebar (citation integrity 8/0).
- **Real corpus state:** 1143 mentions (33 reddit_post + 1110 reddit_comment) · 1380 mention_attributions (39 PRIMARY + 1341 SECONDARY) · 1143 content_type_tags (46 deal / 999 other / 98 review) · 649 aspect_tags (71 PRIMARY + 578 SECONDARY) · **22 aggregate rows** (was 18 pre-Option-3; +4 SECONDARY-only) · 28-entry gold-set JSONL unchanged · 3 preview-brief artifacts for `alienware_16_aurora` (session-6 + two from session 9; latest `alienware_16_aurora_20260507T203215Z.md`) · `llm_cache` has 3 rows for `prompt_version='preview_a1_v1'` (audit-trail; one orphan from the session-9 unfiltered intermediate run, harmless per the never-evict design).
- **Working code:**
  - **Foundation (session 2):** `pulse_check/` storage + config + llm_cache + scraping + tagging.OllamaClient + synthesis.AnthropicClient; `scripts/scrape.py`; Alembic migration applied to `data/pulse_check.db`; 6 example YAML configs.
  - **Wave 1 shell (session 3, visual confirmed session 4):** `pulse_check/api/main.py` (FastAPI factory + `/health` + `/products`/`/pairs` stubs + CORS + error envelope); full `frontend/` Vite+React+TS+Tailwind v3+shadcn-ready scaffold with DESIGN_SYSTEM §3 tokens; three themed route shells render correctly in browser; `scripts/serve.py` dual-server launcher.
  - **Wave 2 tagging (session 3):** `pulse_check/tagging/aspect_classifier.py` (prompt v1 with 11 aspects + 22 synthetic anchors), `pulse_check/tagging/batch.py` (idempotent corpus tagger), `scripts/tag.py` CLI.
  - **Wave 2 gold set (session 3):** `pulse_check/eval/gold_set.py` (stratified sampling, Sonnet labeling via `call_with_cache`, JSONL IO), `scripts/build_gold_set.py`, `scripts/review_gold_set.py` (interactive operator-spot-check CLI).
  - **Wave 2 aggregation (session 4):** `pulse_check/aggregation/a1.py` (`aggregate_a1` rolls `aspect_tags` → `aggregates_aspect_sku` with sorted+deduped `mention_ids` provenance, zero-filled polarity/intensity distributions, flat `net_sentiment`, `verified_share`, by-source/by-recency splits; PRIMARY-only; idempotent delete-then-insert keyed on `(run_id, product_id)`).
  - **Wave 2 scraping + tagging architecture (session 5):** orchestrator `_upsert_products` + dual-sort reddit enqueue + fetcher registration imports; tagging `JsonGenerator` Protocol abstraction + OllamaClient 300s timeout + circuit-breaker error isolation in `batch.py`; synthesis `AnthropicClient._strip_markdown_fences`; CLI `scripts/tag.py --provider {ollama,anthropic}`; first runtime artifacts (real `aspect_tags` + `aggregates_aspect_sku` rows + 28-entry gold-set JSONL).
  - **Bite 6.1 — content-type gate (session 6):** `ContentType` enum + `ContentTypeTag` model + Alembic `4f5dc2929a19`; `pulse_check/tagging/content_type_classifier.py` (Haiku, prompt v1, mention-scoped cache key) + `pulse_check/tagging/content_type_batch.py` (mirrors aspect batch); `scripts/classify_content_type.py` CLI; `--exclude-content-types` strict gate flag on `scripts/tag.py`; 25 new unit tests. Live run: 31/31 mentions classified, 0 parse failures.
  - **Path A throwaway (session 6):** `scripts/preview_brief.py` — Sonnet one-pager exec brief reading aggregates + per-aspect verbatims, informal `[M:<id>]` cite contract; `data/preview_briefs/alienware_16_aurora_*.md` produced (8/8 cites in corpus, 0 fabrication; theatrical aha not output aha — see session-6 narrative).
  - **scrapers-lib BestBuy URL parser extension (session 7):** `tier3/bestbuy.py` now accepts legacy `/site/.../<sku>.p`, modern `/product/.../sku/<sku>`, and modern model-id-only `/product/.../<MODEL_ID>` forms (HTML fallback via `analytics-metadata` meta tag's `"skuId":"<7d>"` payload, `html.unescape`-aware). 8 new tests. CHANGELOG entry under `[Unreleased]/Added`. **NOT yet released** (`_version.py` at 1.2.0 in HEAD with a working-tree edit to 1.2.1 (not from this session — pre-existing diff)).
  - **pulse-check `configs/product_set_smoke_test.yaml` (session 7):** `urls.bestbuy` + `urls.amazon` filled for both products. Amazon canonicalized to `/dp/<ASIN>`. Currently dormant (bite 6.2 retailer-path paused).
  - **pulse-check `docs/url_curation_smoke.md` (session 7):** operator-curated URL checklist (documentation/record).
  - **Bite 6.2-revised — Reddit-deepen (session 8, two rounds):**
    - **scrapers-lib `tier1/reddit.py`:** new `emit_all_comments: bool = False` kwarg on `fetch_reddit_comments` + `parse_reddit_comments` + `_comment_to_mentions`. When True, comments bypass `_fan_out`'s strict per-comment anchor regex and emit unattributed (`attribution=None`); post emission unchanged. CHANGELOG entry under `[Unreleased]/Added`. 4 new tests in `TestEmitAllComments`. **`_version.py` at 1.2.0 in HEAD with a working-tree edit to 1.2.1 (not from this session — pre-existing diff).**
    - **pulse-check `pulse_check/scraping/orchestrator.py`:** new `_enqueue_reddit_comment_followups` enqueues `fetch_reddit_comments(emit_all_comments=True)` on each PRIMARY-attributed Reddit post. New `tests/unit/scraping/test_orchestrator.py` (8 tests, folds session-5 deferred Patch 2 + new comment-enqueue cases).
    - **pulse-check `pulse_check/scraping/comment_inheritance.py` (new):** `apply_comment_inheritance(session) -> CommentInheritanceStats`. Walks unattributed `reddit_comment` mentions, looks up parent post via `metadata_["parent_id"]` (Reddit `t3_<post_id>` link form), inherits parent's PRIMARY products as **SECONDARY** with `attribution_method=REGEX`. Helper `_post_id_from_post_mention_id` extracts `post_id` from `reddit_post_<post_id>_<anchor_id>` mention_id format. Wired into `run_scrape` after `apply_secondary_attribution`. `scripts/scrape.py` updated for tuple-of-three return. `pulse_check/scraping/__init__.py` exports new symbol. `tests/unit/scraping/test_comment_inheritance.py` (11 tests).
    - **pulse-check `pulse_check/tagging/aspect_classifier.py`:** `parse_response` now dedupes within-LLM-response on aspect (keep first occurrence) via `seen_aspects: set[Aspect]`. Reason: Haiku occasionally emits two entries for the same aspect on long comments; the `aspect_tags` UNIQUE constraint failed the whole batch on a single such mention (mid-run crash; both aspect_tags inserts AND llm_cache writes rolled back per session-5 fragility). 1 new test.
    - **`configs/run_smoke_test.yaml`:** `bestbuy_reviews.enabled: false`, `amazon_reviews.enabled: false` (paused per bite 6.4 deferral).
    - **Stale scheduler state cleared:** deleted 4 stale BestBuy + Amazon jobs from `data/scheduler_state.db`; cleared `bestbuy.com` domain backoff. Reddit dedup history preserved.
  - **Option 3 — A1 aggregate PRIMARY/SECONDARY split (session 9):**
    - **Alembic `b8560c93bbd8`** — adds 8 `*_secondary` columns to `aggregates_aspect_sku` via `batch_alter_table`, NOT NULL with server defaults (`0` / `'{}'` / `'[]'`); `down_revision = 4f5dc2929a19`.
    - **`pulse_check/storage/models.py`** — `AggregateAspectSku` gains the 8 mirror columns (`total_mentions_secondary`, `polarity_counts_secondary`, `net_sentiment_secondary`, `intensity_counts_secondary`, `verified_share_secondary`, `by_source_secondary`, `by_recency_secondary`, `mention_ids_secondary`), each with both Python `default` and SQL `server_default`. Imports `text` from `sqlalchemy`.
    - **`pulse_check/aggregation/a1.py`** — extracted `_compute_bucket(tags, mentions, now) -> _BucketResult` helper. `aggregate_a1` builds two attribution-pair sets (`primary_pairs`, `secondary_pairs = SECONDARY-all − primary_pairs` — PRIMARY precedence on dual-attributed pairs), partitions tags accordingly, runs the same 8-field arithmetic twice, writes both halves into one row. Empty bucket → zero/empty fields. `BatchAggregateStats` gained `mentions_contributing_secondary` (default 0). Idempotent delete-then-insert preserved.
    - **`tests/unit/aggregation/test_a1.py`** — 12 → 17 tests. Renamed `test_aggregate_a1_skips_secondary_attributions` → `test_aggregate_a1_routes_primary_and_secondary_into_separate_buckets`. New: `_primary_only_leaves_secondary_columns_empty`, `_secondary_only_path`, `_primary_takes_precedence_over_secondary_pair`, `_skips_secondary_for_out_of_scope_products`, `_idempotent_rerun_with_both_buckets`.
    - **`scripts/preview_brief.py`** — `_render_markdown` adds a "Secondary signal (comment threads; not cited in body):" sidebar showing per-aspect `primary=N · secondary=M (net_sentiment_secondary=X)` for any aspect with `total_mentions_secondary > 0`. `_build_prompts` and `_collect_verbatims` both filter to `total_mentions > 0` (strict isolation: PRIMARY-only into the LLM payload + verbatim corpus; SECONDARY-only rows excluded as they have no PRIMARY mention_ids to cite and would churn the cache). LLM prompt_version unchanged.
    - **`docs/ARCHITECTURE.md`** — §3.3 dual-track table + intro paragraph; §5 tertiary-attribution paragraph (comment-inheritance via `metadata_["parent_id"]`); §6.1 Haiku-deviation pointer; new §6.5 Haiku batch-classifiers; §7.1 split-and-aggregate-twice algorithm.
    - **Live DB rerun:** `aggregate_a1` invoked once on the live corpus → 18 → **22 rows** (4 new SECONDARY-only `(product, aspect)` pairs). `mentions_contributing=71` preserved exactly; `mentions_contributing_secondary=578` newly visible. Sample divergence: `rog_strix_g16` price_value PRIMARY +0.59 vs SECONDARY −0.18; `rog_strix_g16` keyboard PRIMARY 0.0 / SECONDARY −0.48 (52 mentions).
    - **Brief regenerated:** `data/preview_briefs/alienware_16_aurora_20260507T203215Z.md` · 8 cited / 0 fabricated · sidebar rendered. Cache miss vs session-6 row was expected and explained — see "Open items added in session 9".
  - **Synthesis architecture — bites 10.1 + 10.2 (session 10):**
    - **`pulse_check/synthesis/contracts.py` (new)** — Pydantic v2 models locking the §6.3 brief shape: `Claim` (claim_text + cited_mention_ids ≥ 1), `BriefSection` (heading + claims ≥ 1), `BriefNarrative` (brief_title + sections ≥ 1). Plus `NumericalDrift` and `ValidationResult` (is_valid + four lists for fabricated/out-of-context/numerical-drift/empty-claims violations) for the citation validator.
    - **`pulse_check/synthesis/{dedup,selector,brief_writer,citation_validator,orchestrator}.py`** — module skeletons each with typed signatures + docstrings + `raise NotImplementedError("... sub-bite 10.x")`. `__init__.py` re-exports contracts.
    - **`tests/unit/synthesis/test_contracts.py` (new, 7 tests)** — `BriefNarrative.model_dump()` round-trips through `briefs.narrative` JSON column; Pydantic rejects empty citation list / empty text / empty claims / empty sections; `ValidationResult` defaults + drift payload.
    - **`pulse_check/synthesis/dedup.py`** — `cluster_near_duplicates(session, mentions, *, client, prompt_version="a1_dedup_v1") -> dict[str, str]`. Routed to Haiku (`claude-haiku-4-5-20251001`), temperature=0.0, max_tokens=4096; uses `call_with_cache` for deterministic re-runs. Edge cases short-circuit without LLM call: empty list → `{}`, single mention → `{m.mention_id: "c0"}`. Validation: input/output mention_id sets must match exactly. Cluster IDs normalized to opaque `c0`, `c1`, ... in first-seen-in-input order. `client: AnthropicClient` is a required keyword arg (inversion-of-control for tests; was NOT in the 10.1 skeleton).
    - **`tests/unit/synthesis/test_dedup.py` (new, 9 tests, mocked client)** — edge-case short-circuits; 3 distinct → 3 unique clusters; 2 paraphrases + 1 distinct collapse correctly; second call hits cache (`generate_json.call_count == 1`); validation errors on missing/extra mention IDs; malformed JSON variants.
    - **No DB migration** — existing `briefs.narrative` JSON column accepts the shape. **No real Haiku call yet** — dedup is unit-tested with mocks only; real-corpus smoke deferred to 10.4 close.
  - **Bite 10.3 — selector + brief writer + §6.3 four-quadrant lock (session 11):**
    - **`docs/ARCHITECTURE.md` §6.3 "A1 brief layout"** — operator-locked four-quadrant table (Q1 PRIMARY pos ≥3 / Q2 PRIMARY neg ≥3 / Q3 SECONDARY pos ≥1 not in Q1 / Q4 SECONDARY neg ≥1 not in Q2). Up to 3 aspects per quadrant ranked by relevant count desc; up to 3 mentions per aspect ranked by `aspect_tags.intensity` (HIGH > MEDIUM > LOW) with cluster-dedup. Empty Q2 placeholder rule documented; validation rule 1 amended to permit empty `cited_mention_ids` only for that placeholder. Prompt_version `a1_brief_v1`.
    - **`pulse_check/synthesis/contracts.py`** — `Claim.cited_mention_ids` constraint relaxed `min_length=1` → `min_length=0`; docstring notes the placeholder is the sole exemption. Citation validator (10.4) compensates via fabrication checks on any non-empty list.
    - **`pulse_check/synthesis/selector.py`** (full rewrite) — public `select_a1_verbatims(session, *, product_id, aspect, primary_mention_pool, secondary_mention_pool, clusters=None) -> AspectSelection`. New dataclasses `SelectedVerbatim` and `AspectSelection` (per-aspect 4-tuple by polarity × bucket). Per (polarity, bucket): fetch `aspect_tags`, filter to target polarity (NEUTRAL never cited), sort by intensity rank desc + mention_id asc, dedup by cluster, cap at 3. **Deterministic — no LLM call.** Removed `SELECTOR_PROMPT_VERSION` from session-10 skeleton (no prompt = no version).
    - **`pulse_check/synthesis/brief_writer.py`** (full rewrite) — public `write_a1_brief(session, *, client, product, aggregates, selections, prompt_version="a1_brief_v1") -> BriefNarrative`. Pure-Python `_route_aspects_to_quadrants` enforces locked rules. Sonnet (`claude-sonnet-4-6`, T=0, max_tokens=4096) writes only `brief_title` + per-aspect `claim_text`; the writer assembles the §6.3 BriefNarrative deterministically (no fabricated mention IDs possible). Empty Q2 always renders α placeholder. **All-quadrants-empty case short-circuits Sonnet** — emits brief titled `"{display_name} — A1 voice"` + only the placeholder section. `call_with_cache` keyed on the structured Sonnet input payload.
    - **`tests/unit/synthesis/test_contracts.py`** — `test_claim_rejects_empty_citation_list` flipped to `test_claim_allows_empty_citation_list_for_placeholder`.
    - **`tests/unit/synthesis/test_selector.py` (new, 9 tests)** — empty pools, intensity ranking, cap at 3, SECONDARY routing, cluster dedup, NEUTRAL never cited, missing-aspect-tag silently skipped, clusters=None bypass, polarity split.
    - **`tests/unit/synthesis/test_brief_writer.py` (new, 9 tests, mocked AnthropicClient)** — Q1 routing, Q1 cap-at-3 ranked desc, Q2 placeholder + empty citations, Q3 excludes Q1 aspects, low-signal-only routes to Q3, second-call cache hit, missing claim_text raises, empty brief_title raises, no-qualifying-aspects short-circuits Sonnet.
    - **No real Sonnet call yet** — brief writer is mocked-only; first real run deferred to 10.4 close.
- **Not yet started (Wave 2 remainder, prioritized):**
  - **Bite 6.3 — YouTube:** operator URL-seed curation + first end-to-end YouTube fetcher exercise (expect plumbing gaps similar to session-7's Amazon discovery).
  - **Bite 6.4 (deferred) — retailer reviews:** three open items parked — BestBuy network/Akamai timeout diagnostics; pulse-check `result_sink` mapping for `('amazon','post')` and `('bestbuy','post')`; Amazon Strix empty-review-page diagnosis.
  - Synthesis architecture remainder: citation validator + retry loop + `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI (bite 10.4). 10.1–10.3 shipped sessions 10 + 11.
  - Backend `/products`, `/product/:id`, `/mentions?ids=...`, `/brief/:id` real handlers.
  - Frontend atoms (`VerbatimCard`, `AggregateNumber`, `EvidenceDrawer`, `BriefPanel`, `AspectRow`).
  - `/product/:id` page wired end-to-end + Wave 2 exit-criteria check.

## Things to verify when next session resumes

Manual checks the prior session couldn't / didn't do, listed so they don't get lost:

- **Aspect classifier anchors are synthetic** — 22 short verbatims approximating gaming-laptop review language. v2 anchor refinement still expected after first eval iteration; not yet executed.
- **Sonnet gold labeling reuses the Qwen prompt verbatim** — same label space (deliberate). If Sonnet labels look weak during operator spot-check, consider a richer Sonnet-specific prompt as a separate bite.
- **scrapers-lib BestBuy URL HTML-fallback path is unit-tested but never hit production (session 7).** Both BestBuy URLs in session 7 timed out at the network layer before any HTML was returned; the new HTML-fallback regex (`"skuId":"<7d>"` via `_html_unescape`) is verified against the AREA51 fixture but unverified against live Strix HTML. Will revisit when bite 6.4 returns.

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

Added in session 5:
- **Review-vs-deal pre-classifier** — operator's session-5 finding from spot-check. Anchor regex matches deal-roundup posts where the product appears in a list among 10+ others (e.g. "Black Friday Gaming Laptop Deals under $1100"). Result: ~70% of `/top?t=year` corpus is promotional noise rather than substantive opinion. Future fix: a Haiku pre-pass classifying each mention as `review | deal | other` and dropping non-reviews before tagging. Cheap (~$0.001/mention) and high-leverage. Operator-flagged at session-5 close. **Resolved in session 6 — bite 6.1 built the gate; 65% deal contamination confirmed empirically.**
- **LLM cache writes share the SQLAlchemy session** — when the session rolls back on exception, cache rows roll back too. We saw this twice in session 5 (Qwen tag crash → cache lost → re-run did everything from scratch). Cache should run on its own connection/transaction so partial work survives crashes.
- **`tag_corpus_aspects` partial-progress preservation** — currently flushes only at end. Hard crash before circuit-breaker trips loses all in-memory work. Per-N-mention commit (e.g. every 10) bounds the loss; modest contract change ("caller no longer fully owns the transaction").
- **Batch dedup is model-agnostic** — `already_tagged` pre-pass filters on `(taxonomy_version, prompt_version)` only. Switching providers (Ollama → Anthropic) creates rows under the same `prompt_version` that block re-tagging. Three options: extend the pre-pass filter to include `model`; OR bump `prompt_version` when switching providers; OR delete prior rows on provider change. Defer until provider switching is a routine workflow.
- **`OLLAMA_MODEL` default unpin** — `.env.example` pins `qwen2.5:7b-q4_K_M` (specific quantization). Ollama's default `ollama pull qwen2.5:7b` returns a different quant (q4_0). Mismatch caused HTTP 404 in session 5. Either unpin to `qwen2.5:7b` in `.env.example` or document `ollama pull qwen2.5:7b-q4_K_M` as a setup step.
- **`tests/unit/scraping/test_orchestrator.py`** — agent-designed during session 5 (3 cases: insert, idempotent rerun, display_name update). Patch 1 (production) applied; Patch 2 (test) deferred to avoid debug distraction during smoke. Apply early next session — it locks in the upsert behavior with regression coverage.

Added in session 6:
- **A1 aggregator does not honor content-type filter** — bite 6.1's `--exclude-content-types` gate operates at aspect-tag time. `aggregate_a1` rolls up ALL `aspect_tags` rows under `(taxonomy_version, prompt_version)` regardless of mention content-type. Validating that filtering changes the brief shape requires either re-running aspect tagging on a deal-cleaned corpus (destructive, since existing aspect_tags rows would need to be deleted first) OR teaching the aggregator a content_type filter (proposed bite 6.1.5). Likely subsumed by 6.2 corpus expansion; revisit if not.
- **Content-type prompt v1 misclassifies defect reports as `other`** — the screen-flashing post (Path A's most actionable finding) was first-person ownership + clear evaluation, but framed as a help-request. Anchor examples didn't cover defect-report-shaped reviews, so it landed in `other`. Practical mitigation: the right gate invocation is `--exclude-content-types deal` only (keep review AND other). v2 prompt with a defect-report anchor is a future option; premature at n=31.
- **Ruff lint slipped past pre-commit** — `alembic/versions/fa194da18ea1_initial_schema.py` had an I001 import-order error that session 5's commit claimed clean. Auto-fixed at session-6 audit start. Pre-commit setup may not have been active when that file was authored; not investigating further unless it recurs.
- **TASKS.md was stale through session 5** — every checkbox `[ ]` despite Wave 1 being done and Wave 2 ~60%. Reconciled at session-6 audit start; "Last reconciled" line added to header. If future sessions don't update at close, will drift again — flag the discrepancy when it shows up.
- **`runs` table is empty despite aggregates_aspect_sku referencing run_id** — session 5 produced 17 aggregate rows with run_ids that have no matching `runs` row. Foreign keys are not enforced by SQLite by default. Not blocking; flag if a future bite assumes runs/aggregates are joinable.
- **Capability vs output aha distinction** — saved as `feedback_capability_vs_output_aha.md` (memory). Path A confirmed the capability holds; output aha requires corpus density. Apply as evaluation lens at every architectural milestone going forward.

Added in session 7:
- ~~**scrapers-lib `_version.py` deferred bump.**~~ **RESOLVED at session-9 audit start** — `_version.py` is `1.2.1` in HEAD with no working-tree diff; the bump was committed (not by us, between sessions 8 and 9). Earlier session-9 messages still reference "1.2.0 in HEAD with edit to 1.2.1" — that framing is stale.
- **pulse-check `result_sink` does not map `('amazon', 'post')` or `('bestbuy', 'post')`.** Discovered in session 7 when Amazon Alienware fetched cleanly (HTTP 200) but ingestion rejected the row. Latent issue — these mappings were never exercised before. Fix is a small extension (10–30 lines + test); parked in bite 6.4.
- **Amazon Strix returned HTTP 200 but parser found zero inline reviews.** Possible causes: (a) anti-bot stripped page, (b) scrapers-lib selectors stale for this product layout, (c) reviews behind a "see all reviews" link the parser doesn't follow. Diagnose in bite 6.4.
- **BestBuy reachability from this machine.** Both URLs hit curl 28 timeout × 2 → 1h domain backoff (in scrapers-lib scheduler). Could be local network, regional IP, or Akamai escalation. Diagnose with manual curl outside scrapers-lib (and ideally from a different network) when bite 6.4 returns. Backoff auto-expires 1h after last attempt.
- **Run config `paginate: false` for BestBuy.** Smoke config gives only ~5 PDP-embedded reviews per product. Switch to `paginate: true` in `configs/run_smoke_test.yaml` (and `configs/run_demo_2026_04.yaml`) when bite 6.4 wants real density via BestBuy.

Added in session 8:
- **A1 aggregator is PRIMARY-only by design — surfaces as a discoverability gap.** Comment-inheritance produces a 565-row SECONDARY-attributed aspect_tags corpus, and A1's PRIMARY-only filter makes that work invisible at the aggregate layer. Option 3 (dual-track PRIMARY/SECONDARY columns) is the agreed fix. Sub-decisions: (a) which fields to dual-track (4 baseline vs 8 full parity); (b) naming (`*_secondary` suffix vs nested JSON); (c) whether to expose `total_mentions_combined` as a code-computed virtual.
- **`aggregate_a1` arithmetic doc lives only in code, not ARCHITECTURE.** §7.1 step 1 reads "whose `mention_id` is attributed to P" — silent on primary-vs-secondary. Option 3 implementation requires updating §3.3 (column inventory) AND §7.1 (algorithm) to make the dual-track explicit.
- **Comment-inheritance is a new attribution mechanism not described in ARCHITECTURE §5.** Currently §5 covers only "primary at fetch time" + "secondary post-fetch raw_text regex sweep". The parent-post inheritance path is a third mechanism (parent-link-based, no regex on the comment text). ARCHITECTURE §5 needs a third paragraph (drafted in session-8 wrap, ready to paste).
- **scrapers-lib `_version.py` 1.1.0 unbumped, now with two pending releases worth of edits.** Session 7's BestBuy URL extension + session 8's `emit_all_comments` both sit under `[Unreleased]/Added`. Whoever cuts the next release picks the version (likely 1.2.0).
- **content_type breakdown ratios shifted at scale.** At n=31 (session 6) the corpus was ~65% deal. At n=1143 (session 8) it's 4% deal / 87% other / 9% review. The deal-roundup contamination characteristic of `/top?t=year` listings is diluted by the comment corpus, which lands almost entirely in `other`. Re-validate the `--exclude-content-types deal` gate behavior on the new scale before relying on session-6 framing.
- **`apply_comment_inheritance` matches parents only via `metadata_["parent_id"] == "t3_<post_id>"`.** Comments whose parent post is not in our DB are skipped silently (intended). Watch for unexpected 0-inheritance counts on future scrapes — likely indicates a schema/format change in the parent_id metadata.
- **Aspect classifier is now Haiku not Qwen — undocumented in ARCHITECTURE §6.** Per session-5 swap. ARCHITECTURE §6.1 needs a deviation note + §6.5 Haiku batch-classifiers entry covering both `tag_mention_aspects` (Haiku since session 5) and `classify_content_type` (Haiku since session 6).
- **Memory note: no auto-rerun of expensive LLM batches.** Saved as `feedback_no_auto_rerun_on_crash.md` (memory). Pause and ask before restarting expensive LLM batches after a crash.
- **First-contact plumbing budget — pattern.** Untested end-to-end integration paths typically have 2–3 orthogonal failure classes that unit tests don't catch. Future bites that exercise a new source for the first time should budget a discovery phase before committing to "fix all then ship." Applied to bite 6.3 (YouTube): expect plumbing surprises on first run.

Added in session 9:
- **scrapers-lib test count drift +60/+1** (904 pass / 20 skipped vs 844/19 baseline at session-8 close). All green; flagged to operator. Likely external work landed in scrapers-lib between sessions. Confirm baseline before next release decision.
- **`ruff` not installed in scrapers-lib `.venv`.** Audit check #5 couldn't run as specified. `pip install ruff` into that venv (or run via pulse-check's venv pointed at scrapers-lib paths). Non-blocking.
- **`llm_cache` has 3 rows for `prompt_version='preview_a1_v1'`.** Session-6 row + session-9 unfiltered intermediate run row + session-9 strict-isolation final run row. The middle row is an orphan — won't be re-hit, but never-evict is by design (audit trail per ARCHITECTURE §3.4). Cosmetic; flag if it grows unbounded across many preview-brief regens.
- **PRIMARY aspect_tag count drift between sessions, attributable to within-response dedup.** Session 5 produced ~82 PRIMARY aspect_tags; session 8 closed at 71 PRIMARY. Difference is the dedup fix in `parse_response` (session 8) which removed duplicate (mention, aspect) tuples that were previously surviving as separate rows. Expected, not a regression. Implication: re-runs of `aggregate_a1` against historical aspect_tag sets won't reproduce exact session-5 row contents — minor caveat for any future "byte-identical reproducibility" check on PRIMARY values.
- **`runs` table still empty** despite 22 aggregates_aspect_sku rows referencing `run_id='smoke_test'`. Carry-forward from session 6; SQLite doesn't enforce FK by default. Not blocking; flag if a future bite assumes joinability.

Added in session 10:
- **Dedup prompt is unit-tested with mocks, not validated against live Haiku.** `cluster_near_duplicates` has 9 unit tests covering schema/cache/validation, but the prompt itself (`a1_dedup_v1`) has never seen real Haiku output. First real call (in bite 10.4 smoke) needs an eyeball check on cluster quality on the 71-mention PRIMARY pool — especially the "don't cluster opposite-polarity mentions on the same topic" rule, which is the single most fragile constraint.
- **10.1 skeleton signatures don't include `client: AnthropicClient`.** Bite 10.2 added `client` as a required keyword arg on `cluster_near_duplicates` for inversion-of-control. Bites 10.3 (selector, brief_writer) and 10.4 (citation_validator does NOT need it; orchestrator constructs internally) will need similar updates. Watch for the deviation when filling the skeletons; current skeleton signatures will need a small contract bump.
- **`flagged_citation_issues` field is on the validator's `ValidationResult` but not on `briefs.narrative` schema yet.** Soft-warn policy says the orchestrator surfaces violations on the persisted brief. Implementation question for 10.4: encode under `narrative["flagged_citation_issues"]` (no migration; JSON-flexible) vs add a new `briefs` column (migration). Operator did not pre-decide; flag at 10.4 start.
- **Mid-session scope bump.** Session 10 scope was originally locked to "10.1 only" via AskUserQuestion at session start, then bumped to "10.1 + 10.2" mid-session via "commit all and move forward." Both bites landed clean; bumping was the right call. Note for future: mid-session scope changes are fine when the prior bite went clean and momentum is clear, but the session log should record the bump explicitly so the rationale survives.

Added in session 11:
- **No real Sonnet call yet on the brief writer.** 9 unit tests pass against a mocked AnthropicClient; the prompt itself (`a1_brief_v1`) has never seen real Sonnet output. First real run in bite 10.4 close. **Expectation given current corpus** (zero PRIMARY-backed criticism on either product per session-11 audit): Q2 will render the α placeholder for both products on the first real run.
- **Selector trusts caller for PRIMARY/SECONDARY pool disjointness.** No assertion that `set(primary_pool) ∩ set(secondary_pool) == ∅`. A mention in both pools would silently route to both buckets. Current callers (`aggregate.mention_ids` + `mention_ids_secondary` per session-9 PRIMARY-precedence design) honor disjointness; flag if a future caller violates.
- **`Claim.cited_mention_ids` constraint relaxed `min_length=1` → `min_length=0`.** Contract softening to permit the §6.3 placeholder claim (empty Q2). The structural Pydantic guard against accidental empty lists is gone — citation validator (bite 10.4) must enforce that any non-empty list contains only real, in-context mention IDs, AND that empty lists appear only on the placeholder claim.
- **Selector signature deviated from session-10 skeleton.** Skeleton had `SELECTOR_PROMPT_VERSION` + `clusters` parameter implying Sonnet-based selection. Operator approved deterministic-over-Sonnet for cost + test simplicity + evidence-first separation; both removed (`prompt_version` parameter dropped from public signature). Brief writer's Sonnet still writes claim_text per quadrant aspect.
- **Brief writer short-circuits Sonnet when all four quadrants are empty.** Edge case: a product with no qualifying aspects in any quadrant produces a brief titled `"{display_name} — A1 voice"` with only the Q2 placeholder section; no Sonnet call is made. Cost-saving + correct behavior; one branch to remember when reading the 10.4 orchestrator.
- **venv path quirk.** `pytest`/`mypy`/`ruff` only resolve under `.venv/Scripts/python.exe` on this machine — global `python` lacks `pydantic-settings`/`mypy`/`ruff`. Spelled out in next-session starter; consider a README.md (currently pending) entry when README work begins.
- **Brief writer's `_polarity_count` defensively coerces non-int values to 0.** Guards against unexpected types in the JSON `polarity_counts` column. Acceptable defensive coding; flag if a future schema change introduces float/string counts.

---

## Session history (newest first)

### 2026-05-07 — session 11: bite 10.3 — deterministic verbatim selector + Sonnet brief writer (four-quadrant §6.3 layout) + ARCHITECTURE §6.3 A1 layout lock; +18 unit tests, all green

**Context entering.** Session 10 closed at Wave 2 ~80% with synthesis skeleton (10.1) + Haiku dedup (10.2) shipped. Bite 10.3 (selector + brief writer) explicitly deferred to fresh-context conversation because of three product-design questions on sparse-corpus fallback / brief structure / empty-aspect handling that needed operator-design input before code.

**Audit pass.** GREEN. pulse-check **246 pass** · mypy clean on 40 source files · ruff clean. Working tree clean at `bd4e6f9`. Code read on `synthesis/contracts.py` + `synthesis/dedup.py` end-to-end via subagent — both solid; one cosmetic nit at `dedup.py:154` (redundant `str(x)` on a set of already-strings); not blocking. `test_brief_narrative_round_trips_through_briefs_table` confirmed as a real SQLAlchemy round-trip through `briefs.narrative` JSON column. **One environmental gotcha:** `pytest`/`mypy`/`ruff` only resolve under `.venv/Scripts/python.exe` (global `python` lacks the deps); captured in next-session starter.

**Bite pick conversation.** Recommended 10.3 over 10.4/6.3/6.4/frontend with reasoning: 10.4 needs 10.3 first (validator has nothing to validate); 10.3 has product-design questions to surface before code; frontend needs the §6.3 brief shape settled. Operator approved.

**Three product-design questions surfaced — concrete, with corpus numbers.** A subagent gathered §6.3 spec position + current throwaway behavior + real-corpus sparsity numbers from the live SQLite. Headline finding: **0 of 18 PRIMARY aggregates satisfy the spec's "3 pos + 3 neg" rule** on either product (e.g. `rog_strix_g16 performance: 6 pos, 0 neg`). This converted Q1 from a "fallback" question into the primary-rule question.

**Operator decisions (locked, all flagged in-conversation before code):**
- (Q1=a) **Verbatim selector:** per aspect, up to 3 PRIMARY-pos + up to 3 PRIMARY-neg, **no padding**, cap 6.
- (Q2 layout pixels) **Parked** for the operator's claude.ai/design prototype to be shared at frontend bite. JSON contract decidable now without it.
- (Q3 = c-extended → four quadrants) **Brief layout:** four sections in fixed order: high-confidence strengths/weaknesses (PRIMARY ≥ 3 of polarity), low-signal strengths/weaknesses (SECONDARY ≥ 1 of polarity, not in §1/§2). Per quadrant: up to 3 aspects, ranked by relevant count desc.
- (Q3 placeholder = α) **Empty Q2** renders one placeholder claim `"No top-of-mind criticism in PRIMARY chatter — see §4 below"` with `cited_mention_ids=[]`.
- **Operator pushback on my proposed symmetric "3 each / 3 each" target.** A subagent feasibility check confirmed both products fail symmetric layout (0 high-confidence cons on either, structural per how Reddit attribution works — criticism lives in comments = SECONDARY). Asymmetric with α placeholder for empty Q2 was the resolution.
- **Selector route:** **deterministic** over Sonnet — cheaper, simpler tests, evidence-first separation (selector picks IDs; Sonnet writes claim_text in the brief writer).
- **High-confidence threshold:** ≥ 3 PRIMARY mentions of that polarity. (Lowering to ≥ 2 doesn't help — cons stay at 0 on the live corpus anyway.)

**ARCHITECTURE.md §6.3 update.** Added "A1 brief layout (operator-locked, session 11)" subsection — four-quadrant table + ranking rules + placeholder claim contract. Validation rule 1 amended to permit empty `cited_mention_ids` only for the placeholder claim. `prompt_version` `a1_brief_v1` documented.

**Implementation.** See "Working code → Bite 10.3 — selector + brief writer + §6.3 four-quadrant lock (session 11)" in Current state above for the full file-level inventory. Tests parity with `test_dedup.py` mocked-client pattern (9 selector + 9 brief_writer = 18 new).

**Verification.**
- `pytest tests/unit/` → **264 pass** (was 246; +18).
- `mypy pulse_check/` → clean on 40 source files (no count change — selector + brief_writer replaced existing skeletons).
- `ruff check pulse_check/ tests/` → clean.

**Real Sonnet call still pending.** Brief writer is mocked-only. First real run is part of bite 10.4 close on the live 71-mention PRIMARY pool. Expectation per corpus reality: Q2 (high-confidence cons) renders α placeholder for both pilot products.

**Commits:**
- `<sha-tbd>` — Session 11 bite 10.3: deterministic selector + Sonnet brief writer + §6.3 four-quadrant lock + 18 tests; SESSION_LOG + TASKS update.

**Deferred to session 12:** Bite 10.4 — citation validator (4 soft-warn checks per TESTING §6) + retry loop + `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI + first real Haiku+Sonnet smoke. Operator's claude.ai/design prototype still queued for the frontend bite.

### 2026-05-07 — session 10: synthesis package skeleton + §6.3 brief contracts (bite 10.1) + Haiku near-duplicate dedup (bite 10.2); +16 unit tests, +6 mypy files, all green

**Context entering.** Session 9 closed at Wave 2 ~75% with Option 3 shipped (PRIMARY/SECONDARY dual-track aggregates) but **work was sitting uncommitted** on the working tree. First action of session 10 was to commit it (`8d6304d`). Synthesis architecture queued as the natural Option-3 follow-on — productionize what `preview_brief.py` previewed.

**Audit pass.** GREEN. pulse-check 230 pass · mypy 34 files clean · ruff clean. Session-9 diff cross-checked against SESSION_LOG narrative — no divergence. One audit-flagged risk (session-9 work entirely uncommitted) resolved by committing.

**Plan agent on synthesis architecture.** Read PRD/ARCHITECTURE/TASKS/SESSION_LOG + `scripts/preview_brief.py` + `pulse_check/synthesis/anthropic_client.py` + `pulse_check/llm_cache/cache.py`. State of layer: `llm_cache` + `briefs` table + `synthesis/anthropic_client.py` exist; net-new: dedup, selector, production brief writer (prototype uses wrong schema), citation validator. Proposed 4 sub-bites (10.1 skeleton + contracts → 10.2 Haiku dedup → 10.3 Sonnet selector + brief writer → 10.4 citation validator + orchestrator). Recommended starter: 10.1, ~1.5h, no LLM spend.

**Operator decisions (3, all approved before code):**
- (a) **Brief schema:** §6.3 canonical `sections/claims/cited_mention_ids` (over the prototype's flat `headline/findings/watchout`). Wave 4 frontend was designed against §6.3.
- (b) **Citation validator:** **soft-warn** (write the brief with `flagged_citation_issues` field) over hard-fail. Small corpus + ±5% drift on counts will be brittle from Sonnet; soft-warn lets the operator read the warning rather than block the brief.
- (c) **Session 10 scope:** initially "10.1 only," bumped mid-session to "10.1 + 10.2" via "commit all and move forward," then wrapped before 10.3 (which has product-design questions deserving fresh-context conversation).

**Bite 10.1 — synthesis package skeleton + §6.3 contracts.**
- **`pulse_check/synthesis/contracts.py` (new)** — Pydantic v2 models. `Claim` (claim_text + cited_mention_ids ≥ 1), `BriefSection` (heading + claims ≥ 1), `BriefNarrative` (brief_title + sections ≥ 1) — exact §6.3 shape. Plus `NumericalDrift` and `ValidationResult` for the citation validator.
- **Skeleton modules** — `synthesis/{dedup,selector,brief_writer,citation_validator,orchestrator}.py`, each typed signature + docstring + `raise NotImplementedError("... sub-bite 10.x")`.
- **`pulse_check/synthesis/__init__.py`** — re-exports contracts.
- **`tests/unit/synthesis/test_contracts.py` (new, 7 tests)** — `BriefNarrative.model_dump()` round-trips through `briefs.narrative` JSON column; Pydantic rejects empty citation list / empty text / empty claims / empty sections; `ValidationResult` defaults + drift payload.
- **No DB migration** — existing `briefs.narrative` JSON column accepts the shape.

**Bite 10.2 — Haiku near-duplicate dedup.**
- **`pulse_check/synthesis/dedup.py`** — `cluster_near_duplicates(session, mentions, *, client, prompt_version="a1_dedup_v1") -> dict[str, str]`. Routed to Haiku (`claude-haiku-4-5-20251001`), temperature=0.0, max_tokens=4096; uses `call_with_cache` for deterministic re-runs. Edge cases short-circuit without LLM call (empty list → `{}`, single mention → `{m.mention_id: "c0"}`). Cache payload sorted by mention_id for stability across mention-list orderings. Validation: input/output mention_id sets must match exactly; raises `LlmResponseError` on missing/extra IDs or non-list `assignments`. Cluster IDs normalized to opaque `c0`, `c1`, ... in first-seen-in-input order so downstream code is decoupled from Haiku's free-form labels. Added `client: AnthropicClient` as a required keyword arg (inversion-of-control for tests; was NOT in the 10.1 skeleton signature).
- **`tests/unit/synthesis/test_dedup.py` (new, 9 tests, mocked client)** — edge-case short-circuits (no SDK call); 3-distinct → 3 unique clusters; 2 paraphrases + 1 distinct collapse correctly; second call hits cache (`generate_json.call_count == 1`); validation errors on missing/extra mention IDs; malformed JSON variants (non-object, non-list assignments).
- **No real Haiku call yet** — 10.2 is unit-tested with mocks. Real-corpus smoke deferred to 10.4 close.

**Final regression at session close:** `pytest tests/unit/` → **246 pass** (was 230; +16 from contracts + dedup tests). `mypy pulse_check/` → clean on **40 source files** (was 34; +6 synthesis modules). `ruff check` → clean.

**Commits:**
- `8d6304d` — Session 9 work (committed at session 10 open).
- `e60dd95` — Session 10 bite 10.1: synthesis package skeleton + §6.3 brief contracts.
- `0b4bb9e` — Session 10 bite 10.2: Haiku near-duplicate dedup with cache + validation.

**Deferred to session 11:** Bite 10.3 (Sonnet selector + production brief writer; product-design questions on sparse-corpus fallback + brief structure + empty-aspect handling) and bite 10.4 (citation validator + retry loop + `synthesize_a1` orchestrator + `scripts/synthesize.py` CLI). Operator's frontend prototype from claude.ai/design (BriefPanel/scorecard mimic) is queued for the frontend bite — to be shared when that bite starts.

### 2026-05-07 — session 9: Option 3 — A1 aggregate PRIMARY/SECONDARY dual-track (migration + aggregator + tests + ARCHITECTURE + preview-brief renderer/strict-isolation filter); live rerun + brief regen

**Context entering.** Session 8 closed at Wave 2 ~70% with Option 3 locked at session close: dual-track PRIMARY/SECONDARY columns on `aggregates_aspect_sku`, run arithmetic twice, expose both buckets to `preview_brief.py`. Three sub-decisions to settle at session-9 audit close: (a) field scope — 4 baseline vs 8 full parity; (b) naming — `*_secondary` suffix vs nested JSON; (c) virtual `total_mentions_combined`.

**Audit pass.** GREEN with three housekeeping notes. pulse-check 225 pass · mypy 34 files clean · ruff clean. **scrapers-lib 904 pass · 20 skipped** (drift +60/+1 vs 844/19 baseline; flagged, all green). **scrapers-lib `_version.py` already `1.2.1` in HEAD with no working-tree diff** — session-7/8's two-pending-releases open item resolved (committed between sessions, not by us). ruff not installed in scrapers-lib `.venv` — check #5 couldn't run. DB sanity matched expected (mentions=1143, attributions 39P/1341S, content_type 46/999/98, aspect_tags 649, aggregates 18, alembic `4f5dc2929a19`, gold-set 28, brief artifact present). Code read-through on session-8 edits all PASS.

**Option 3 sub-decisions confirmed.** (a) Full 8 fields. (b) `*_secondary` suffix. (c) NO virtual `total_mentions_combined` — preserves no-hidden-weighting principle. Rationale per session-8 plan: storage cost trivial at ~22 rows; SQL legibility favors suffix; bucketed display lets UI/operator decide aggregation explicitly.

**Implementation.**
- **Migration `b8560c93bbd8`** — generated via `alembic revision`, then hand-written `upgrade()`/`downgrade()`. `batch_alter_table` adds 8 columns NOT NULL with server defaults: `total_mentions_secondary` (Integer, `0`), `polarity_counts_secondary` (JSON, `'{}'`), `net_sentiment_secondary` (Float, `0.0`), `intensity_counts_secondary` (JSON, `'{}'`), `verified_share_secondary` (Float, `0.0`), `by_source_secondary` (JSON, `'{}'`), `by_recency_secondary` (JSON, `'{}'`), `mention_ids_secondary` (JSON, `'[]'`). `down_revision = 4f5dc2929a19`.
- **`pulse_check/storage/models.py`** — `AggregateAspectSku` gains the 8 mirror columns with both Python `default` (`0` / `0.0` / `dict` / `list`) and SQL `server_default` matching the migration. Imports `text` from `sqlalchemy`.
- **`pulse_check/aggregation/a1.py`** — extracted `_compute_bucket(tags, mentions, now) -> _BucketResult` helper to factor out the shared 8-field arithmetic; added `_empty_bucket()` for the zero-state. `aggregate_a1` builds `primary_pairs` and `secondary_pairs_all` from `mention_attributions`, derives `secondary_pairs = secondary_pairs_all − primary_pairs` (PRIMARY precedence on dual-attributed pairs), partitions tags accordingly, runs `_compute_bucket` twice per `(product, aspect)` and emits one row carrying both halves. `BatchAggregateStats` gained `mentions_contributing_secondary` (default 0, preserves back-compat). Updated docstring to describe both buckets and the empty-side semantics. Idempotent delete-then-insert preserved.
- **`tests/unit/aggregation/test_a1.py`** — 12 → **17 tests**. Renamed legacy `test_aggregate_a1_skips_secondary_attributions` → `test_aggregate_a1_routes_primary_and_secondary_into_separate_buckets` with new SECONDARY-bucket assertions on top of the existing primary ones. New tests: `_primary_only_leaves_secondary_columns_empty` (legacy preserved), `_secondary_only_path` (PRIMARY zeros + SECONDARY populated), `_primary_takes_precedence_over_secondary_pair` (no double-count), `_skips_secondary_for_out_of_scope_products`, `_idempotent_rerun_with_both_buckets`. Updated coverage docstring.
- **`scripts/preview_brief.py`** — `_render_markdown` extended to take `aggregates` and append a "Secondary signal (comment threads; not cited in body):" sidebar listing `aspect: primary=N · secondary=M (net_sentiment_secondary=X)` for any aspect with `total_mentions_secondary > 0`. **Strict-isolation fix** (operator-confirmed mid-session): `_build_prompts` and `_collect_verbatims` filter to `total_mentions > 0` before constructing the LLM payload + verbatim corpus, since SECONDARY-only rows have empty PRIMARY `mention_ids` (no cite-able verbatims) and would just churn the cache as the SECONDARY corpus grows. PROMPT_VERSION unchanged.
- **`docs/ARCHITECTURE.md`** — §3.3 dual-track table (8 PRIMARY rows + 8 `*_secondary` rows) + intro paragraph explaining the bucketed semantics and no-combined principle; §5 tertiary-attribution paragraph (parent-link comment-inheritance via `metadata_["parent_id"]`); §6.1 Haiku-deviation pointer to §6.5; new §6.5 "Haiku — batch classifiers" covering `tag_mention_aspects` + `classify_content_type`; §7.1 algorithm rewritten for partition-then-twice (PRIMARY precedence note included).

**Verification.**
- pulse-check **230 pass** (was 225; +5 new tests) · mypy clean on 34 source files · ruff clean. scrapers-lib unchanged.
- `alembic upgrade head` ran cleanly: `4f5dc2929a19 → b8560c93bbd8`. `aggregates_aspect_sku` now has 21 columns (was 13); existing 18 rows got server-default zero/empty values.
- **Live `aggregate_a1` rerun** (free, local, no LLM): `BatchAggregateStats(groups_seen=22, aggregates_upserted=22, mentions_contributing=71, mentions_contributing_secondary=578)`. 18 → **22 rows** (4 new SECONDARY-only `(product, aspect)` pairs, e.g. `support_warranty: primary=0 / secondary=5`). PRIMARY mentions_contributing=71 preserved exactly vs pre-Option-3 baseline; PRIMARY columns unchanged per row. Sample divergence flagging dual-track value:
  - `rog_strix_g16` aesthetics: PRIMARY 1 / SECONDARY 91; net_sentiment −1.0 / **−0.33**.
  - `rog_strix_g16` price_value: PRIMARY 17 / SECONDARY 77; net_sentiment +0.59 / **−0.18** (most striking divergence — comment threads disagree with post sentiment on price).
  - `rog_strix_g16` keyboard: PRIMARY 1 / SECONDARY 52; net_sentiment 0.0 / **−0.48**.
  - `alienware_16_aurora` price_value: PRIMARY 6 / SECONDARY 45; +0.67 / +0.07.

**Brief regeneration.** Two passes during the session:
1. **First pass (intermediate, before strict-isolation fix):** `data/preview_briefs/alienware_16_aurora_20260507T185904Z.md`. Cache miss vs session-6 row (~17s Sonnet HTTP). Citation integrity 7/0. Sidebar rendered. Findings cycled vs session-6 (`price_value / build_quality / display` → `price_value / display / performance`). Ruled "narrative variance, not regression" but flagged as input-side noise: SECONDARY-only rows leaked into LLM payload as zero-count entries.
2. **Second pass (after strict-isolation filter):** `data/preview_briefs/alienware_16_aurora_20260507T203215Z.md`. Cache miss again (~17s) — operator hypothesis "filter restores session-6 cache hit" disproven. Diagnosis: PRIMARY data did drift between session-6 and session-9, not from Option 3 but from the session-8 within-response dedup re-tag (PRIMARY aspect_tags 82 → 71 as duplicate `(mention, aspect)` tuples were pruned). Different PRIMARY counts per aspect → different aggregates → different LLM payload. Cache miss is correct given the data shift; the filter is still load-bearing for **future** SECONDARY-only row additions which won't churn the cache. Citation integrity 8/0. Sidebar rendered. Today's run is the new session-9 baseline cache row.

**Mid-session decision: strict isolation in `_build_prompts` + `_collect_verbatims`.** Operator picked stance (i) over (ii) "leave as-is" after I surfaced the cache-miss-after-row-set-growth issue. Reasoning: defensive against future drift, no semantic change for this run (zero-count rows weren't driving findings anyway), small ~5-line edit. Memory not added — single-session call, not a generalizable rule.

**Key decisions (all flagged in-conversation when made).**
- Option 3 sub-decisions (a) full 8 / (b) suffix / (c) no virtual — operator confirmed; rationale recorded above.
- PRIMARY precedence on dual-attributed `(mention, product)` pairs (`secondary_pairs = SECONDARY-all − primary_pairs`) — preserves "every mention = 1.0".
- Strict-isolation filter on `_build_prompts` + `_collect_verbatims` — applied mid-session after cache-miss diagnosis.
- Live `aggregate_a1` rerun authorized as part of "go" since it's local + free; preview-brief regens authorized per operator request and explicitly held back behind separate confirmation given Sonnet $.
- `_version.py` open item ruled resolved at audit, not deferred again — it was already done in HEAD.

**Artifacts created/modified (session 9).**
- `alembic/versions/b8560c93bbd8_add_aggregate_a1_secondary_bucket_.py` (new).
- `pulse_check/storage/models.py` (+8 columns, `text` import).
- `pulse_check/aggregation/a1.py` (full rewrite of body; new helpers; `BatchAggregateStats` extension).
- `tests/unit/aggregation/test_a1.py` (rename + 5 new tests + docstring update).
- `scripts/preview_brief.py` (sidebar render + strict-isolation filters).
- `docs/ARCHITECTURE.md` (5 sections updated: §3.3 table+intro, §5 tertiary paragraph, §6.1 deviation note, new §6.5, §7.1 algorithm).
- `data/pulse_check.db` — 22 aggregate rows (was 18); 8 new columns populated.
- `data/preview_briefs/alienware_16_aurora_20260507T185904Z.md` (intermediate, orphan cache row).
- `data/preview_briefs/alienware_16_aurora_20260507T203215Z.md` (final, current baseline).
- Sonnet spend: 2× preview-brief calls (~$0.05 each, both cache miss). No Haiku spend (session-8 already covered the 1143-mention classify+tag pass).

**Final regression baselines.**
- pulse-check: **230 pass · mypy clean on 34 source files · ruff clean.**
- scrapers-lib: 904 pass · 20 skipped · ruff blocked by missing install (audit flag, not a session-9 regression).
- Alembic head: **`b8560c93bbd8`**.

**Session closed at Wave 2 ~75%.** Output aha unlocked at the aggregate layer (PRIMARY/SECONDARY divergence visible per row); preview brief renders the sidebar over real data; ARCHITECTURE catches up to the past three sessions of deviations (Haiku swap, content-type gate, comment-inheritance, dual-track). Synthesis architecture (Haiku dedup → Sonnet selector → brief writer → citation validator) is the natural next bite to productionize what `preview_brief.py` previewed; YouTube (bite 6.3) and retailer (bite 6.4) and backend/frontend Wave 2 finish are also viable. Next session resumes with audit pass per the standard handoff pattern, then operator picks the bite.

---

### 2026-05-07 — session 8: bite 6.2-revised (Reddit-deepen via orchestrator extension + scrapers-lib `emit_all_comments` + comment inheritance) + Option 3 lock

**Context entering.** Session 7 closed at Wave 2 ~65% with bite 6.2-revised (Reddit-deepen via comments on existing primary-attributed posts) approved as the actual density unlock. Mission: implement bite 6.2-revised, observe density delta, decide aggregator response. Operator framing: ultrathink mode, agent-delegated context, terse reporting.

**Audit pass.** All GREEN. 205 pulse-check tests pass; mypy clean on 42 source files; ruff clean. DB matched expected (33 mentions, 82 aspect_tags, 17 aggregates, 31 content_type_tags). Alembic head `4f5dc2929a19`. Path A artifact present. Code read-through on session-7 BestBuy URL parser extension verified all doctrine items. The 2 unclassified Reddit mentions from session 7 deferred to bite 6.2-revised pipeline (rolled in cleanly).

**Bite 6.2-revised — round 1: orchestrator extension.** Added `_enqueue_reddit_comment_followups` to `pulse_check/scraping/orchestrator.py` — enqueues `fetch_reddit_comments` on each PRIMARY-attributed Reddit post in DB. New tests in fresh `tests/unit/scraping/test_orchestrator.py` (8 tests, folding in session-5 deferred Patch 2 + new comment-enqueue cases). Live run produced **6 new comment mentions out of likely 200–1500.** Diagnosis: scrapers-lib's `_fan_out` applies a strict per-comment anchor regex at fetch time; most comments don't repeat the product anchor in every line and were dropped. **Density gain: trivial.**

**Operator decision — Option B chosen: loosen the filter via inheritance.** Reasoning: comment-by-comment regex requires the anchor in every line (rare in real Reddit threads); the parent-post PRIMARY attribution already proves the thread is about the product, so all comments under that thread are at minimum SECONDARY-eligible. Implementation routed through three coordinated edits:

**scrapers-lib edit — `tier1/reddit.py` `emit_all_comments` kwarg.**
- New `emit_all_comments: bool = False` on `fetch_reddit_comments` + `parse_reddit_comments` + `_comment_to_mentions`. When True, comments bypass `_fan_out`'s strict per-comment anchor regex and emit unattributed (`attribution=None`); post emission unchanged.
- 4 new tests in new `TestEmitAllComments` class.
- CHANGELOG entry under `[Unreleased]/Added`. **`_version.py` at 1.2.0 in HEAD with a working-tree edit to 1.2.1 (not from this session — pre-existing diff)** (deferred bump from session 7, now with two pending releases worth of edits).
- 844 pass · 19 skipped (was 840/19).

**pulse-check edit — `pulse_check/scraping/comment_inheritance.py` (new).**
- `apply_comment_inheritance(session) -> CommentInheritanceStats` iterates unattributed `reddit_comment` mentions, looks up parent post via `metadata_["parent_id"]` (Reddit `t3_<post_id>` link form), inherits parent's PRIMARY products as **SECONDARY** with `attribution_method=REGEX` (chosen for schema uniformity, even though the link is a parent_id lookup not a regex match).
- Helper `_post_id_from_post_mention_id` extracts `post_id` from `reddit_post_<post_id>_<anchor_id>` mention_id format.
- Wired into `run_scrape` after `apply_secondary_attribution`. `scripts/scrape.py` updated for tuple-of-three return. `pulse_check/scraping/__init__.py` exports new symbol.
- New test file `tests/unit/scraping/test_comment_inheritance.py` (11 tests).
- Orchestrator's comment-fetch enqueue now passes `emit_all_comments=True`.

**pulse-check edit — `pulse_check/tagging/aspect_classifier.py` within-response dedup.**
- `parse_response` dedupes within-LLM-response on aspect (keep first occurrence) via a `seen_aspects: set[Aspect]` guard.
- **Reason:** mid-run crash. Haiku occasionally emits two entries for the same aspect on long comments; the `aspect_tags` UNIQUE constraint failed the whole batch. Per session-5 fragility, both aspect_tags inserts AND llm_cache writes were rolled back. Dedup fix re-ran from scratch.
- 1 new test in `test_aspect_classifier.py`.

**Mid-run crash + memory note.** During the live re-tag pass, hit an `IntegrityError` on duplicate aspect tuples. Surfaced cost-vs-residual-risk before re-running. **New memory saved: `feedback_no_auto_rerun_on_crash.md`** — pause and ask before restarting expensive LLM batches after a crash.

**Run-config edit — `configs/run_smoke_test.yaml`.** `bestbuy_reviews.enabled: false`, `amazon_reviews.enabled: false` (paused per bite 6.4 deferral; URLs in `product_set_smoke_test.yaml` remain populated as documentation).

**Stale scheduler state cleared.** Deleted 4 stale BestBuy + Amazon jobs from `data/scheduler_state.db`; cleared `bestbuy.com` domain backoff. Reddit dedup history preserved.

**Live pipeline (round 2 result).**
- Corpus: 39 → **1143 mentions** (33 reddit_post + 1110 reddit_comment). 35× expansion.
- mention_attributions: 39 primary (33 post + 6 comment) + **1341 secondary** (largely the inherited comment attributions).
- content_type breakdown over 1143: **46 deal / 999 other / 98 review.** The 65% deal contamination characteristic of `/top?t=year` listings (session 6, n=31) does not hold at this scale.
- aspect_tags: 95 → **649** (71 PRIMARY-attributed + 578 SECONDARY-attributed).
- **A1 aggregate rows: still 18, unchanged.** `aggregate_a1` is PRIMARY-only and the 565 new comment aspect_tags are all on SECONDARY-attributed mentions. **The expansion is invisible at the aggregate layer.**
- Cost: ~$10.45 in Haiku spend across classify + tag + one mid-run crash.

**Operator decision locked at session close: Option 3 — split A1 aggregate schema into PRIMARY/SECONDARY columns.**
Concrete plan: add `total_mentions_secondary`, `polarity_counts_secondary` (json), `net_sentiment_secondary` (float), `mention_ids_secondary` (json) — possibly `intensity_counts_secondary`, `verified_share_secondary`, `by_source_secondary`, `by_recency_secondary` for full parity. Existing primary columns untouched. Alembic migration. `aggregate_a1` runs the same 8-field math twice. Tests for both. Update `preview_brief.py` if needed. Estimated 1–2h. Three sub-decisions to settle at session-9 audit close before coding: (a) which fields (4 baseline vs 8 full parity); (b) naming convention (`*_secondary` suffix vs nested JSON blob); (c) virtual `total_mentions_combined` (recommend NO — preserves no-hidden-weighting principle).

**Why Option 3 over alternatives.** Option 1 (drop PRIMARY-only filter) loses the structural distinction between "post is about product X" and "comment in a thread about product X". Option 2 (mix into single columns) blurs the signal. Option 3 is the lowest-cost path that preserves PRIMARY-only A1 semantics, surfaces the SECONDARY signal as a parallel number, and respects no-hidden-weighting.

**Key decisions (all flagged in-conversation when made).**
- Option B (loosen filter via inheritance) over Option A (loosen scrapers-lib's `_fan_out` regex universally) — keeps post-attribution machinery untouched at default; pulse-check owns the inheritance semantics.
- `attribution_method=REGEX` for inherited comment attributions despite the link being a parent_id lookup — schema uniformity over a new enum value.
- Pause-and-ask after the mid-run crash rather than re-run silently (saved as `feedback_no_auto_rerun_on_crash.md`).
- Within-response dedup fix lives in `parse_response`, not at SQL upsert layer — cheaper test surface, single place to reason about Haiku idiosyncrasies.
- Scheduler state stale-job cleanup done. Deferred bite 6.4 will re-enqueue cleanly when it returns.
- `_version.py` bump deferred again.

**Artifacts created/modified (session 8).**
- `..\scrapers-lib\scrapers_lib\tier1\reddit.py` (`emit_all_comments` kwarg).
- `..\scrapers-lib\tests\tier1\test_reddit.py` (4 new tests).
- `..\scrapers-lib\CHANGELOG.md` (new entry).
- `pulse_check/scraping/orchestrator.py` (`_enqueue_reddit_comment_followups`).
- `pulse_check/scraping/comment_inheritance.py` (new).
- `pulse_check/scraping/__init__.py` (re-export).
- `pulse_check/tagging/aspect_classifier.py` (`parse_response` dedup).
- `scripts/scrape.py` (new tuple-of-three return).
- `tests/unit/scraping/test_orchestrator.py` (new, 8 tests).
- `tests/unit/scraping/test_comment_inheritance.py` (new, 11 tests).
- `tests/unit/tagging/test_aspect_classifier.py` (1 new test).
- `configs/run_smoke_test.yaml` (BestBuy + Amazon disabled).
- `data/pulse_check.db` — corpus 33 → 1143; ~$10.45 in Haiku spend.
- `data/scheduler_state.db` — stale jobs cleared.
- Memory: `feedback_no_auto_rerun_on_crash.md` + MEMORY.md update.
- Docs: `docs/SESSION_LOG.md` + `docs/TASKS.md` updated at session close.

**Final regression baselines.**
- pulse-check: **225 pass · mypy clean on 34 source files · ruff clean.** (mypy CLI now `mypy pulse_check`; `scripts` dropped — count agreed with prior baselines, kept verbatim.)
- scrapers-lib: **844 pass · 19 skipped · ruff clean on edited files.**
- Alembic head: `4f5dc2929a19` (no migration this session).

**Session closed at Wave 2 ~70%; corpus density unlocked, aggregator gap surfaced, Option 3 locked as the next bite.** The bite-6.2-revised pipeline proves the comment-inheritance pattern works end-to-end (1143-mention corpus produced cleanly); the aggregate layer is the bottleneck to **output aha** at the new density. Next session resumes with audit pass per the standard handoff pattern; then sub-decision close on Option 3 fields/naming/virtual; then ARCHITECTURE doc updates; then Alembic migration; then aggregator extension; then test pass; then `preview_brief.py` regen for the actual aha-test on enriched data.

---

### 2026-05-06 — session 7: bite 6.2 retailer-pivot (scrapers-lib URL parser extension + first end-to-end retailer scrape attempt + strategic pivot to Reddit-deepen)

**Context entering.** Session 6 closed at Wave 2 ~65% with capability validated, contamination quantified, output aha gated by corpus density. Recommended next bite was 6.2 (corpus expansion via BestBuy + Amazon review fetchers). Operator framing: ultrathink mode, agent-delegated context, terse reporting.

**Audit pass.** All GREEN. 205 pulse-check tests pass; mypy clean on 42 source files; ruff clean. DB matched expected (products=2, mentions=31, aspect_tags=82, aggregates=17, content_type_tags=31 with 20 deal / 8 other / 3 review). Alembic head `4f5dc2929a19`. Path A artifact present. All 9 doctrine items on session-6 edits PASS. **Cosmetic flag:** session-6 starter prompt referenced `data/gold_set/aspect_classifier_v1.jsonl`; actual path is `data/gold_sets/aspect_tagging_v1.jsonl` (28 entries either way). Corrected in session-7's next-session starter.

**Bite 6.2 scoping.** Operator approved 6.2 (corpus expansion) over 6.1.5 (aggregator filter) and prompt-v2 refinement. Asked for smoke-set scope (2 products only) with operator-side URL curation. Drafted `docs/url_curation_smoke.md` checklist; operator filled in 4 URLs.

**URL parser block — scrapers-lib's BestBuy parser was outdated.** 2 of 4 URLs (BestBuy / both products) used the modern `/product/<slug>/<MODEL_ID>/sku/<7d>` and `/product/<slug>/<MODEL_ID>` forms; scrapers-lib's `_SKU_PATH_RE` only matched legacy `/site/.../<7d>.p`. Operator authorized the sibling-lib edit with explicit framing: "I want the scrapers lib to change so that it works for this project, this project is the key user of bestbuy and amazon scraping."

**scrapers-lib edit — `tier3/bestbuy.py` URL parser extension.**
- Added `from html import unescape as _html_unescape` (escape-aware HTML extraction).
- Replaced single `_SKU_PATH_RE` with tuple `_SKU_PATH_RES` containing both legacy `/(\d{7})\.p` and modern `/sku/(\d{7})` patterns.
- Added `_SKU_META_RE = re.compile(r'"skuId"\s*:\s*"(\d{7})"')` for the HTML-fallback regex.
- `_extract_sku(url)` → `_extract_sku(url, html=None)` (back-compat). Tries URL-path regexes first, then `?skuId=<sku>` query, then — only if `html` provided — extracts from PDP HTML's `analytics-metadata` meta tag (via `_html_unescape` so escaped `&quot;skuId&quot;` matches too).
- Updated paginate=False call site (line 243): passes already-fetched HTML through.
- Updated paginate=True call site (line 132): try `_extract_sku(url)` first; on `ValueError`, lazily fetch PDP via `_fetch_pdp`, retry with HTML. Adds at most one extra HTTP hop, only for URL forms without SKU.
- 8 new tests in `TestExtractSku` (parametrized modern-path + escaped/unescaped HTML + URL-precedence + raise + AREA51 fixture verification).
- CHANGELOG entry under `[Unreleased]/Added`.
- **`_version.py` NOT bumped** — operator approved v1.2.0 in conversation but I deferred to avoid rolling pre-existing pending [Unreleased] changes (HP fetcher + asus URL fix) into a release decision unilaterally. Flagged as deviation.
- 840 scrapers-lib tests pass + 19 skipped; ruff clean; pre-existing mypy errors (4) unrelated to session-7 edits. pulse-check 205 tests still pass.

**pulse-check edit — `configs/product_set_smoke_test.yaml`.** Patched 4 URL slots; Amazon URLs canonicalized to `/dp/<ASIN>` form (stripped `?ref=...&crid=...` query strings).

**Pipeline run — three orthogonal blockers exposed.** Ran `scripts/scrape.py --run-config configs/run_smoke_test.yaml`. Result:
- **BestBuy / Alienware:** curl 28 timeout × 2 → 1h domain backoff. Network-level — no bytes returned.
- **BestBuy / Strix:** same — curl 28 timeout. **HTML-fallback path never tested in production.** New code is unit-tested against fixture but unverified against live Strix HTML.
- **Amazon / Alienware:** HTTP 200 fetched, but pulse-check's `result_sink` rejected with `unknown scrapers-lib (source, source_type) = ('amazon', 'post')`. pulse-check ingest-mapping bug (latent — never exercised before since Amazon was never scraped end-to-end).
- **Amazon / Strix:** HTTP 200, "no inline reviews found". Could be (a) anti-bot stripped page, (b) parser selectors stale for this product layout, (c) reviews behind a "see all" link the parser doesn't follow.
- Side effect: orchestrator added 2 new Reddit mentions (dual-sort picked up new /new posts since session 6); these are now in DB but unclassified + untagged. Mentions=33, content_type_tags=31. **DB inconsistency.**

**Strategic pivot — operator stepped back.** "Do we actually need retailer website reviews? Is reddit + youtube better for effort vs reward?" Honest analysis confirmed: yes, pivot. Retailer reviews give verified-purchase signal but text is short-form, the fragility tax (Akamai, anti-bot, parser drift) is permanent, and we just hit three orthogonal first-contact failures. Reddit comments on the 32 existing primary-attributed posts are the highest-leverage unlock — same already-validated source path, no operator URL curation, expected 10–50× corpus expansion. YouTube is a strong second priority but with the same untested-fetcher friction we just experienced on Amazon.

**Revised plan (operator-locked):**
- **Bite 6.2-revised — Reddit-deepen.** Add `fetch_reddit_comments` enqueue to orchestrator; pull comments on the primary-attributed Reddit posts. Re-run classify → tag → aggregate. Report density delta. **Stop after to reassess before YouTube.**
- **Bite 6.3 — YouTube.** Operator-curated seed list (~10–20 URLs); exercise YouTube fetcher end-to-end; absorb the 1–2 plumbing surprises that are likely to surface.
- **Bite 6.4 (deferred) — retailer reviews.** Three open items parked: BestBuy network, Amazon ingest mapping, Amazon Strix empty page. scrapers-lib URL parser extension stays in place (zero cost, useful when 6.4 returns). YAML URLs stay as documentation.

**Sunk-cost accounting (acknowledged honestly).** ~1.5h of session-7 work on scrapers-lib BestBuy URL parser + YAML curation is **not wasted** — it's correct code that will be needed when retailer reviews come back. The first-contact pipeline run found three real bugs; the lesson is that first-contact discovery should have its own scoped phase before committing to "fix all then ship."

**Key decisions (all flagged in-conversation when made).**
- Sibling-lib edit (scrapers-lib) authorized explicitly by operator framing pulse-check as the "key user" of BestBuy + Amazon scraping.
- Auto-fix the BestBuy parser via regex + HTML fallback rather than asking operator to find different URL forms (operator confirmed the new form is what BestBuy serves now).
- HTML SKU extraction via `analytics-metadata` meta tag (operationally critical for BestBuy itself, more reliable than JSON-LD; recovery cost ~5 lines if it ever breaks).
- `_version.py` bump deferred (release-management decision, not session-7 scope).
- Pivot to Reddit-deepen after honest cost-benefit analysis (operator-confirmed at session-7 close).

**Artifacts created/modified (session 7).**
- `..\scrapers-lib\scrapers_lib\tier3\bestbuy.py` (URL parser extension, ~30 lines).
- `..\scrapers-lib\tests\tier3\test_bestbuy.py` (8 new tests in `TestExtractSku`).
- `..\scrapers-lib\CHANGELOG.md` (new entry under `[Unreleased]/Added`).
- `pulse-check\configs\product_set_smoke_test.yaml` (4 URL slots populated).
- `pulse-check\docs\url_curation_smoke.md` (operator-filled curation checklist).
- `data\pulse_check.db` — 2 new Reddit mentions added by scrape attempt (unclassified, untagged).
- `..\scrapers-lib\<scheduler-state>` — 1h domain backoff for `bestbuy.com` (auto-expires).

**Session closed at Wave 2 ~65%** (unchanged from session 6 in narrative-progress terms; one path matured, retailer-path explored-then-deferred, Reddit-deepen identified as actual unlock). Operator triggered close-out at ~14% context use to clear and start fresh for bite 6.2-revised.

---

### 2026-05-06 — session 6: audit + Path A preview + bite 6.1 (content-type gate)

**Context entering.** Session 5 closed at Wave 2 ~60% with brief preview path A vs B pending. Mission: audit session 5 deliverables, settle the path question, execute. Operator framing: ultrathink mode, agent-delegated context, terse reporting.

**Audit pass.**
- Regression: 180 tests pass, mypy clean on 31 source files (NOTE: session-5 starter said 38; the count was wrong but no real regression), **ruff had 1 fixable I001** in `alembic/versions/fa194da18ea1_initial_schema.py`. Auto-fixed (`ruff check --fix`).
- DB sanity matched session-5 brief: products=2, mentions=31, aspect_tags=82, aggregates=17, gold-set 28 entries.
- **TASKS.md reconciliation** — discovered every checkbox was empty despite Wave 1 + most of Wave 2 being done. Operator chose to fold the reconciliation into the audit (option a). Marked Wave 1 complete, Wave 2 tagging + gold-set + aggregation done, Wave 2 synthesis/API/frontend remaining; added "Last reconciled" date header; flagged Qwen→Haiku swap as a session-5 deviation.

**Path A — exec one-pager preview brief.** Operator chose Path A + Alienware product + exec format. Built `scripts/preview_brief.py` (throwaway): reads aggregates_aspect_sku for one product, builds per-aspect verbatim corpus capped at 4 mentions × 3000 chars per aspect, asks Sonnet for `{headline, findings: [3], watchout}` JSON via existing `AnthropicClient` + `call_with_cache`. Includes informal citation integrity check (counts cited IDs vs in-scope IDs). One Sonnet call, ~16s, 8/8 cites in corpus, 0 fabrication. Output: `data/preview_briefs/alienware_16_aurora_*.md`.

**Operator + Claude verdict — theatrical aha, not output aha.** Honest read of the brief content:
- Finding #1 (price_value @ $899) — corpus-shape artifact: 5 of 6 cites are deal-roundup posts (the contamination session 5 flagged). Alienware product team already runs the promotions and has sales-conversion data; this finding tells them their own pricing is visible.
- Finding #2 (build_quality "brand rehabilitation") — n=2. Two ownership posts is not a brand turn.
- Finding #3 (display flashing defect) — n=1. The most actionable item but most likely already in Dell's support CRM.
- Why it FEELS aha: Sonnet's prose ties 8 unrelated mentions into a coherent narrative; 8/8 cite discipline reads like rigor; "watchout" framing is procedurally exec-shaped.

**Operator framing locked.** "Capability aha on the system, [not] output aha yet because of not enough mentions being processed." Saved as memory `feedback_capability_vs_output_aha.md` — pilot-evaluation lens for every future architectural milestone.

**Bite 6.1 — content-type gate.**
- **Schema.** `ContentType` enum (review|deal|other) in `storage/enums.py`; `ContentTypeTag` model (mention-scoped, no `product_id`; uniqueness `(mention_id, prompt_version)`) in `storage/models.py`. Alembic autogen + manual cleanup (autogen referenced `pulse_check.storage.types.UtcDateTime` without import; replaced with `sa.DateTime(timezone=True)` to match initial-schema style). Migration `4f5dc2929a19` applied; 31 → 32 column inventory verified.
- **Classifier.** `pulse_check/tagging/content_type_classifier.py` — Haiku-backed (default model `claude-haiku-4-5-20251001`); prompt v1 with 3 buckets, tie-breaking rules, 6 anchor examples (2 per bucket); mention text clipped to 3000 chars (intent decisive in opening). Imports `JsonGenerator` Protocol from `aspect_classifier` (DRY for the Protocol; cheaper than premature shared-types module). `parse_response` returns `None` on unknown content_type (caller drops without crashing the batch).
- **Batch.** `pulse_check/tagging/content_type_batch.py` mirrors `aspect` batch: 3-consecutive-infra-failure circuit breaker, parse-failure isolation, idempotency on `(mention_id, prompt_version)`. Iterates UNIQUE in-scope mention_ids (not pairs), since content_type is mention-scoped.
- **CLI.** `scripts/classify_content_type.py` — Anthropic-only (Haiku); cache-aware so re-runs are free.
- **Gate.** `tag_corpus_aspects` gained `exclude_content_types: frozenset[ContentType] | None`. **Strict semantics:** when set, mentions WITHOUT a content_type_tag are also skipped (operator must classify first). `--exclude-content-types {review,deal,other} ...` flag wired to `scripts/tag.py` with multi-value support.
- **Tests.** 25 new unit tests across 3 files: classifier (prompt determinism, parse_response branches, cache hit/miss/scope), batch (happy path, idempotency, scoping, dedup-per-mention), aspect-batch filter (excluded-deal skipped, unclassified strictly skipped, no-filter no-op). All green.
- **Live run.** `python scripts/classify_content_type.py --run-config configs/run_smoke_test.yaml` — 31/31 classified in ~25s, 0 parse failures, 0 infra failures. Cost: ~$0.05.

**The diagnostic.** 65% of corpus is deal-roundup contamination (vs session-5 eyeball estimate 70%):
- All mentions: 20 deal / 8 other / 3 review
- Alienware (primary): 6 deal / 2 other / 3 review
- ROG Strix (primary): 14 deal / 6 other / **0 review** — Strix has zero reviews; A1 on Strix is structurally infeasible right now.

**One genuine surprise.** The screen-flashing defect post (Path A's most actionable finding) was classified `other`, not `review`. It IS first-person ownership + clear critique, but framed as a help-request ("screen flashing randomly... great machine but..."). v1 prompt anchors didn't cover defect-report-shaped reviews. **Implication:** right gate policy is `--exclude-content-types deal` only (keep review AND other). Filtering to review-only would lose the only actionable signal in the corpus.

**Path A re-run on cleaned corpus deliberately NOT done.** Doing it cleanly requires teaching the A1 aggregator to honor the content-type filter (the aggregator currently rolls up ALL `aspect_tags` rows). That's a separate bite (6.1.5, optional) and likely subsumed by corpus expansion (6.2). Out of scope for 6.1 as scoped.

**Conclusion.** Capability is locked in (synthesis layer works end-to-end with citation discipline). **Corpus density is the gate to output aha, not synthesis architecture.** Post-deal-filter density: alienware=5, strix=6 mentions per product — too thin for meaningful synthesis. The actual unblock is bite 6.2 (corpus expansion via BestBuy + Amazon review fetchers; Wave 1 wrappers exist, needs URL curation operator-side).

**Key decisions (all flagged in-conversation when made).**
- Reconcile TASKS.md as part of audit pass (operator explicit).
- Auto-fix the ruff lint rather than investigate why pre-commit missed it (cosmetic, 1-line).
- Path A first, not Path B — fast aha checkpoint before committing to Wave 2 synthesis architecture.
- Honest verdict (theatrical aha) over enthusiastic acceptance — operator confirmed framing.
- Tag-time gate with strict semantics (require classification) over permissive (let unclassified through).
- v1 prompt with 6 anchor examples, no gold set yet (premature at n=31; eyeball is appropriate scale).
- Decline to re-run Path A on filtered data without aggregator changes (out of bite scope; respects pilot-focus discipline).

**Artifacts created (session 6).**
- `pulse_check/storage/enums.py` edit: `ContentType` added.
- `pulse_check/storage/models.py` edit: `ContentTypeTag` added + import.
- `pulse_check/tagging/content_type_classifier.py` (new, ~230 lines).
- `pulse_check/tagging/content_type_batch.py` (new, ~150 lines).
- `pulse_check/tagging/__init__.py` edit: re-export new symbols.
- `pulse_check/tagging/batch.py` edits: `exclude_content_types` param + filter logic + stats field.
- `scripts/classify_content_type.py` (new, ~75 lines).
- `scripts/tag.py` edits: `--exclude-content-types` flag + plumbing.
- `scripts/preview_brief.py` (new, throwaway, ~210 lines).
- `alembic/versions/4f5dc2929a19_add_content_type_tags.py` (new migration; manually cleaned from autogen).
- `tests/unit/tagging/test_content_type_classifier.py` (new, 16 tests).
- `tests/unit/tagging/test_content_type_batch.py` (new, 5 tests).
- `tests/unit/tagging/test_batch.py` edits: 3 new filter tests.
- `docs/TASKS.md` edits: full reconciliation against current state + Wave 2 deviation flag for Qwen→Haiku swap.
- `data/pulse_check.db` — 31 new `content_type_tags` rows; ~$0.05 in Haiku spend.
- `data/preview_briefs/alienware_16_aurora_*.md` (Path A artifact).
- Memory: `feedback_capability_vs_output_aha.md` + MEMORY.md update.
- Auto-fix: `alembic/versions/fa194da18ea1_initial_schema.py` (ruff I001 cleanup).

**Session closed at Wave 2 ~65%; capability validated, contamination quantified, output aha gated by corpus density.** Operator triggered close-out at 20% context use ("well beyond I like being"). Next session resumes with audit pass per the standard handoff pattern; recommended next bite is 6.2 (corpus expansion).

---

### 2026-05-05 — session 5: real-corpus smoke + Qwen→Haiku swap

**Context entering.** Session 4 closed at Wave 2 ~50% with smoke-scrape green-light pending. Session 5's mission: audit session 4 work + run the real smoke pipeline + arrive at first real aggregates. Operator framing: non-technical, decision-shaped reporting; agents for low-context delegation; ultrathink tone.

**Audit pass.** 180 pass · mypy clean on 38 files · ruff clean. Code read-through on `aggregation/a1.py` + tests confirmed all six doctrine points (every mention=1.0, sorted+deduped `mention_ids`, polarity/intensity zero-filled distributions, PRIMARY-only filter, idempotent `(run_id, product_id)` delete-then-insert, `flush()` only). GREEN.

**Smoke scrape — 4 iterations to land usable corpus.**
1. First run: 0 mentions. Cause: `scrapers-lib`'s `@register` decorators fire on module import; `pulse-check`'s orchestrator never imported the fetcher modules (`tier1.reddit`, `tier3.bestbuy`, `tier3.amazon`). Fix: 2 import lines in `orchestrator.py`.
2. Second run: 1 mention from `r/GamingLaptops/new`. Reality of low-traffic recent posts.
3. Third run: 5 subreddits added to smoke config (`r/Alienware`, `r/buildapc`, `r/SuggestALaptop`, `r/laptops`). Yielded 3 mentions total. Real bottleneck: `/new` returns the most recent 100 posts per sub, dominated by random topics.
4. Fourth run: orchestrator now enqueues BOTH `sort="new"` AND `sort="top", time_filter="year"` per subreddit (verified scrapers-lib supports the kwargs via `**fetch_options` forwarding). 32 mentions, 28 primary, 14 secondary. **10× jump.**

**Tag step — 4 architectural fixes before producing tags.**
1. `OLLAMA_MODEL` mismatch: `.env` pinned `qwen2.5:7b-q4_K_M` but operator had `qwen2.5:7b` loaded → HTTP 404. Switched `.env`.
2. `OllamaClient.timeout` 120s → 300s; one mention took >120s on Qwen.
3. `LlmParseError` per-mention catch in `batch.py`: Qwen returned `{"tags": null}` on long Reddit posts (3 of 7 calls). One bad output mustn't kill the batch.
4. Circuit breaker for `LlmConnectionError`/`LlmResponseError`: halt cleanly after 3 consecutive infra failures so partial work commits via the standard flush + caller-commit chain.

**Even with all four fixes, Qwen capability ceiling hit.** Long Reddit posts caused 4-min waits returning empty/null tag lists. Operator-approved swap to Haiku per CLAUDE.md fallback rule. Implementation: `JsonGenerator` Protocol in `aspect_classifier.py` (both `OllamaClient` and `AnthropicClient` already had matching `generate_json` signatures); `--provider {ollama,anthropic}` flag in `scripts/tag.py`. Haiku tag run produced **82 aspect tags from 28 primary attributions in ~1 min for ~$0.15** with zero parse failures + zero infra failures.

But the FIRST Haiku run also failed: every response was a parse error. Cause: Haiku wraps JSON in ```json…``` markdown fences even when explicitly told not to (Anthropic has no equivalent of Ollama's `format=json` hard mode). Fix: `_strip_markdown_fences` helper in `AnthropicClient.generate_json` before `json.loads`.

**Gold set.** Sonnet labeled all 28 primary mentions for ~$0.30 → `data/gold_sets/aspect_tagging_v1.jsonl`. First gold-set build hit a missing-Product-rows bug — sampler's INNER JOIN on `Product` returned 0 because `products` table was empty (orchestrator never upserted from config). Manual backfill unblocked; agent designed proper fix; Patch 1 (production) applied to `orchestrator.py` (`_upsert_products`); Patch 2 (3-test file) deferred to a next-session bite.

**Operator spot-check (5 random entries instead of 28-entry full review — efficiency move).** **Critical finding:** 4 of 5 random entries are deal-roundup posts that match the anchor regex but contain no substantive opinion content; only entry 5 was a real ROG Strix G16 review. Sonnet labeled correctly throughout: substantive input → accurate labels; deal noise → zero labels (correct call). Bottleneck is corpus precision, not labeling system. Captured as deferred item #1 (review-vs-deal pre-classifier).

**A1 aggregator first run on real data.** 17 (product, aspect) rollup rows — 8 for Alienware 16 Aurora, 9 for ROG Strix G16. Findings characteristically right: Alienware shows **software_experience −1.00** (Command Center pain) + universal performance/build praise; ROG Strix shows **price_value +0.86** (value champion) + **thermals 0.00** (runs hot reputation confirmed) + **aesthetics −1.00** (the "ugly" entry-5 post).

**Key technical decisions (all flagged in-conversation when made).**
- Reddit `/top?t=year` augmentation, not `/new` replacement (additive — keeps recent breaking content too).
- Provider swap mid-corpus rather than fixing Qwen prompt v2 (gets to working pilot fast; Qwen revisit becomes a separate research workstream).
- Spot-check 5 random entries instead of 28 sequential interactive review (statistical sufficiency for calibration).
- `JsonGenerator` Protocol over `Union[OllamaClient, AnthropicClient]` (cleaner abstraction; future provider adds drop in).

**Decision deferred to next session.** Brief preview path A vs B (above).

**Artifacts created (session 5).**
- `pulse_check/scraping/orchestrator.py` edits: fetcher imports, dual-sort reddit enqueue, `_upsert_products`.
- `pulse_check/tagging/aspect_classifier.py` edits: `JsonGenerator` Protocol, dropped concrete `OllamaClient` import.
- `pulse_check/tagging/ollama.py` edit: timeout 120s → 300s.
- `pulse_check/tagging/batch.py` edits: per-mention error catch + circuit breaker.
- `pulse_check/synthesis/anthropic_client.py` edits: `_strip_markdown_fences` + integration.
- `scripts/tag.py` edits: `--provider` flag + Anthropic branch.
- `configs/run_smoke_test.yaml` edit: 5 subreddits.
- `.env` edit: `OLLAMA_MODEL=qwen2.5:7b`.
- First runtime data: `data/pulse_check.db` populated (2 products, 31 mentions, 82 aspect_tags, 17 aggregates_aspect_sku) + `data/gold_sets/aspect_tagging_v1.jsonl`.

**Session closed at Wave 2 ~60%; real corpus validated, brief preview path pending operator choice.** Smoke scrape proves the pipeline end-to-end; first gold set + aggregates unlock the eval gate; deferred items are refinements, not blockers. Next session resumes with audit pass per the standard handoff pattern.

---

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
