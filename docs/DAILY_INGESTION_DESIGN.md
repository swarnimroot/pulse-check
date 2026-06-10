# Daily Ingestion + Weekly Analysis — Design Note

**Status:** Decisions locked by operator (session 45, 2026-06-10). **Step 1 (daily
collector) shipped session 45** — `scripts/daily_collect.py` +
`pulse_check/scheduling/daily_state.py` + `Settings.daily_collector_state_path` + 15
unit tests; first live run is operator-gated. Steps 2–4 (per-week aggregate snapshots ·
weekly-analyze entry point · trend read path) not yet built. See ARCHITECTURE §14.1.
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

2. **Weekly analysis entry point.** Runs aspect tagging (already incremental) + an
   aggregate snapshot. Skips brief synthesis by default.

3. **Time-bucketed aggregates — the one genuine schema decision.** Today
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

   *Decision needed from operator.* Recommendation: **(A)** — least disruptive, ships
   the trend capability without a schema migration.

4. **No scheduler is added in-repo.** There is no active cron today (only a manual
   quarterly dry-run chain, `scripts/refresh.py`). The operator runs the daily/weekly
   jobs via local Windows Task Scheduler and owns the timing. We provide the commands.

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
