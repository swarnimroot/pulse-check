# Daily Ingestion + Weekly Analysis — Design Note

**Status:** Decisions locked by operator (session 45, 2026-06-10). **Step 1 (daily
collector) shipped session 45** — `scripts/daily_collect.py` +
`pulse_check/scheduling/daily_state.py` + `Settings.daily_collector_state_path` + 15
unit tests; first live run is operator-gated. **Steps 2–4 shipped session 46** —
`scripts/weekly_analyze.py` (weekly-analyze entry point) +
`pulse_check/scheduling/weekly_snapshot.py` (`snapshot_run_id` + `ensure_run_row`;
option A per-week snapshot ids, no migration) + `GET /api/trend/{product_id}` (trend
read path, backend only — UI deferred until weekly snapshots accumulate) + 10 unit
tests. First live weekly run is operator-gated. See ARCHITECTURE §14.1.
**Why this exists:** the pilot was designed as a quarterly batch. This note proposes
shifting to a *standing pipeline* so we stop losing Reddit data. It contradicts the
prior "quarterly cadence / reject rolling-data dependency" locks, so per the doc
protocol it is written for explicit approval before any code.

> **Plain-English sections are §1–§4 and §7.** §5–§6 are implementation detail the
> operator may skip and trust.

---

## 1. The problem

Reddit only lets you page back ~1000 items in a subreddit's "new" feed, and busy subs
churn through that in days. There is **no reliable way to buy back history**. So:

- **Today is day zero.** Whatever we don't capture is gone forever.
- We need to start collecting **now**, **daily**, to build a real time series.
- There is no historical-backfill mechanism, and we are not building one.

## 2. The principle

**Capture-once, append-only, never overwrite.**

- A mention's **text and its original timestamp never change** — that's all we need.
- We bucket sentiment by the post's timestamp → trend over time falls out for free.
- A **deleted** Reddit post stays in our DB and keeps feeding the trend.
- The only thing that drifts on Reddit is the **upvote score** — but this project
  counts **every mention = 1.0** (no score weighting, core principle). So we record
  score once as metadata and never re-poll it. Score drift is irrelevant to the metric.
- When a daily scrape re-sees a still-live post, we **dedup by stable ID and skip it** —
  not overwrite, not duplicate. First sighting wins.

## 3. Three cadences (decoupled)

The expensive part is the LLM. We separate collection from analysis so no single run is
huge, time-consuming, or costly:

| Cadence | Does what | Cost |
|---|---|---|
| **Daily** | Scrape + store raw posts/comments, **all current sources** | Cheap — no LLM, bandwidth only |
| **Weekly** | Classify + aspect-tag **only new mentions** + recompute aggregate snapshot | Moderate — LLM on the delta only |
| **Quarterly / on-demand** | Regenerate briefs (the Sonnet narrative layer) | Expensive — only when data has materially moved |

Raising the analysis cadence to weekly means the quarterly brief run reads
already-tagged data — it never re-does a giant classification pass.

## 4. What we already have (the good news)

The current architecture is mostly ready:

- **Append-only is already how it works.** Mentions are keyed by a stable upstream ID
  (`mention_id` PK); on re-scrape an existing row is skipped, never overwritten
  (`ingester.py`). Scrape is idempotent today.
- **Both timestamps are stored:** `published_at` (original post time — the trend axis)
  and `first_seen_at` (when we ingested it — lets us slice "new since last run").
- **Aspect tagging is already incremental** — it pre-loads already-tagged pairs and only
  sends new/untagged mentions to the LLM (`tagging/batch.py`).
- **Comments are already first-class** — Reddit comments are stored as mentions with
  `source_type=REDDIT_COMMENT` and a `parent_id`. No new table needed.

## 5. What needs to change *(implementation — skippable)*

Four real pieces of work, smallest to largest:

1. **Daily collector entry point.** A thin wrapper over the existing `scripts/scrape.py`
   that runs against the standing product/source config and **logs gaps** (if a day was
   missed, the next run notes it; it just pages the "new" feed as deep as Reddit allows —
   no special backfill). Operator schedules it locally and times it to avoid overlap with
   the other project on this machine (GPU/network/Reddit-rate-limit contention is the
   operator's to stagger).

2. **Weekly analysis entry point.** *(Shipped session 46 — `scripts/weekly_analyze.py`.)*
   Runs aspect tagging (already incremental) + an aggregate snapshot. Skips brief
   synthesis by default. Tagging defaults to **Qwen/ollama** (the volume tagger per
   CLAUDE.md routing); `--provider anthropic` switches to Haiku. `--as-of YYYY-MM-DD`
   overrides the snapshot week for backfill / deterministic re-runs. No separate
   weekly-state file — the snapshot `run_id`s *are* the run trail, so weekly
   gap-detection is deferred as YAGNI (unlike the daily tier, where the perishable feed
   makes a gap unrecoverable and worth flagging).

3. **Time-bucketed aggregates — the one genuine schema decision.** *(Shipped session 46
   — `pulse_check/scheduling/weekly_snapshot.py`, option A.)* Today
   `aggregates_aspect_sku` is keyed by a single reused `run_id` and **overwritten in
   place** (delete-then-insert), with no date dimension. To read trends we need the
   aggregate history to persist across weeks instead of being clobbered. Two options:

   - **(A) Recommended — per-week snapshot id.** Each weekly run writes aggregates under
     a time-stamped id (e.g. `run_2026_w24`). Delete-then-insert stays scoped to that
     week's id, so prior weeks are untouched. A trend = the sequence of snapshots.
     Minimal: reuses the existing `run_id` key, no migration, no constraint change.
     Cost: `run_id` semantics shift from "the pilot run" to "a weekly snapshot."
   - **(B) Alternative — explicit `period` column.** Add a date-bucket column +
     widen the unique constraint to `(run_id, product_id, aspect, period)`. More
     explicit, but a migration and touches the aggregation + API read paths.

   *Resolved: operator chose **(A)** (locked decision 2).* Implemented as
   `snapshot_run_id(when) → run_YYYY_wNN` (ISO week) + `ensure_run_row` (creates the
   backing `runs` FK row each week — SQLite doesn't enforce the FK but Postgres will).
   `aggregate_a1` is reused unchanged; its delete-then-insert is already scoped to
   `(run_id, product_id)`, so a per-week id leaves prior weeks intact.

   **Trend read path (step 4).** `GET /api/trend/{product_id}` returns the sequence of
   snapshots oldest-first by `computed_at`, each carrying per-aspect `total_mentions` +
   `net_sentiment`. It includes **all** of a product's aggregate snapshots — the pilot
   `run_wave5_v1` becomes the first trend point — rather than filtering to
   weekly-pattern ids, which keeps the read honest and avoids brittle id-format
   matching. Backend only; a charting UI is deferred until several weekly snapshots
   accumulate (a single snapshot plots one dot).

4. **Scheduler artifacts in-repo (session 46).** `scripts/daily_collect.{ps1,xml}` +
   `scripts/weekly_analyze.{ps1,xml}` — Windows Task Scheduler wrapper + import template
   pairs mirroring the quarterly `refresh_quarterly.*`. Registered live on the operator
   machine: **daily collect 05:00 daily** (scrape-only, no GPU — overlap-irrelevant);
   **weekly analyze 07:00 Sunday** (Qwen on the shared GPU — staggered 8h past the other
   project's 23:00 LLM run, which lasts ~3–6h, so the two never contend for the GPU). The
   operator owns the timing; the `.xml` files carry `PLACEHOLDER_*` slots for portability.

## 6. Accepted limitations *(implementation — skippable)*

- **A missed day = permanently lost Reddit data.** No backfill. We log the gap; we don't
  recover it.
- **Score evolution is not tracked** — by design (mention = 1.0).
- **Edited post bodies** keep their first-seen text (we never overwrite). Acceptable.
- **Per-mention re-classification doesn't re-run** if taxonomy/prompt version is
  unchanged — same as today's incremental tagging. A taxonomy bump still forces a
  re-tag of the affected scope (existing behavior).

## 7. Out of scope for this note

- **Source-list cleanup + broadening coverage** (more subreddits/sources, increasing
  product coverage) is a related but separate workstream the operator flagged — handled
  on its own, not blocked by this design.
- **Generation/year tagging** (2024/2025/2026 variants within a product family) is a
  separate parked thinking note — family stays the identity; generation would be an
  optional tag layered on later. Not part of this ingestion design.

---

## Locked decisions (operator, 2026-06-10)

1. **Three-cadence model approved** — daily collect / weekly analyze / quarterly brief.
2. **Aggregates trend storage = (A) per-week snapshot id.** No schema migration; each
   weekly run writes under a time-stamped id and prior weeks are untouched.
3. **Weekly aggregate = full corpus-to-date** (no trailing window). Every weekly snapshot
   rolls up all mentions accumulated so far.

---

## Collection-layer fixes (session 46)

Building the daily collector surfaced two source-access problems and one
operational gotcha. Full mechanics in ARCHITECTURE §5.

- **Reddit JSON API is dead for us → switched to `.rss`.** Reddit 403-blocks the
  unauthenticated JSON endpoints for our IP (no UA/TLS/curl_cffi workaround;
  OAuth registration closed). New `.rss` fetchers (`reddit_rss` /
  `reddit_comments_rss`) get posts **and** comments via the public Atom feeds
  over plain httpx + a browser UA. Comment-inheritance preserved. Comment
  deepening is capped at the 50 newest posts/run (reddit 429s the `.rss`
  endpoint after ~100 requests) and self-paced ~1 s/request.
- **YouTube now actually transcribes caption-less videos.** Enabled the
  `audio_fallback` path (yt-dlp + faster-whisper, CPU) so PoToken-gated /
  caption-less videos yield a whisper transcript instead of being dropped.
  Video selection now matches title **+ description**. A pre-fetch dedup skips
  already-transcribed videos so daily re-sweeps don't re-run whisper. CPU-only —
  no GPU contention with the weekly Qwen pass or another project's GPU job.
- **Scheduler queue is persistent — clear it when changing fetchers.** The
  Scheduler's `data/scheduler_state.db` retains pending jobs across runs. After
  switching reddit from JSON to `.rss`, stale JSON jobs lingered and their 403s
  tripped a domain-wide backoff that skipped the new jobs. Delete
  `data/scheduler_state.db` once after a fetcher-source change; it's a transient
  job queue (the corpus lives in the main DB) and is rebuilt each run.
