# pulse-check — Stakeholder Briefing

*Draft · 2026-05-20 · Pilot snapshot from `run_wave5_v1`*

> **Status:** This is a draft to anchor a stakeholder conversation. Numbers are live (53 SKUs, 5,061 public mentions). Spotlight SKUs are illustrative — swap them for whichever three best fit your audience.

---

## 1. What is pulse-check?

A product-listening pilot for the PC manufacturer side. Reads what owners are actually saying across reddit, news, video, and review sites; structures it by aspect (thermals, performance, keyboard, display, battery, build, software, price, support, aesthetics, portability); and produces evidence-cited briefs per SKU and head-to-head comparisons across the lineup.

**Scope of this snapshot:**

| | |
|---|---|
| Tracked SKUs | 53 gaming laptops (Alienware · ASUS · Acer · HP · Lenovo · MSI) |
| Public mentions analyzed | 5,061 |
| Aspects per SKU | 11 |
| Refresh cadence | Quarterly (~$60-100 / year LLM spend at steady state) |
| Provenance | Every claim in a brief cites real mention IDs; verbatims rendered from DB, never LLM output |

---

## 2. What's surfaced — three spotlight SKUs

Each brief below is the live `a1_brief_v2` output for that SKU under `run_wave5_v1`. Full versions (with verbatims and citation drill-down) are in the app at `/pulse-check`.

### 2.1 Lenovo Legion 7 Pro 16 — competitor winning the segment

**78 mentions analyzed · avg net sentiment +0.196 · briefed across 11 aspects**

What owners praise:
- **Raw power** — generational leap from prior-gen RTX hardware; users upgrading from 3070 Ti / GTX 1080 report 2-3× improvements.
- **OLED display** — buyers switching from IPS describe it as "on another level" and a decisive upgrade.
- **Value-versus-rivals** — better panel quality + case construction than similarly priced competitors at the 5070 Ti tier.

What owners complain about:
- **Driver / software instability** — bricked display after a GeForce driver update, full system black-screen crashes.
- **CPU overheating** — recurring pattern across multiple Legion Pro 7i generations; one owner needed repeated heatsink + motherboard service.
- **Chassis compromises in pre-builts** — Indian buyers of pre-built 5080 / 5090 models report a smaller 80 Wh battery installed to save ~$13, leaving a hollow void in the chassis.

**Implication for stakeholders:** Lenovo is winning the premium-mid segment on the strength of OLED + raw performance, despite real software/thermal pain. The opening is in **stability** and **complete-build integrity** — Lenovo's own QA gaps are documented in owner-voice.

---

### 2.2 Alienware 18 Area-51 — own-brand reception

**54 mentions analyzed · avg net sentiment -0.085 · briefed across 11 aspects**

What owners praise:
- **Class-leading raw power** — RTX 5090 sustains near-full 175 W TGP, gaming frame rates 5-15 % above the average RTX 5090 laptop.
- **Durable chassis** — owners describe it as "exceptionally rigid"; one user's previous Alienware survived seven years of daily use.
- **CherryMX keys** — low-profile mechanical keyboard called out as among the most comfortable in any gaming laptop.

What owners complain about:
- **AWCC software** — Alienware Command Center repeatedly criticized as a downgrade from older versions; lacks profile import/export, sometimes hangs.
- **Premium price + stability concerns** — at $3,500-$4,400, multiple owners report recurring BSODs and game crashes that persist after factory resets.
- **Heaviest in class** — at 4.2 kg, roughly 600 g heavier than even the MSI Titan 18.
- **Worst battery in 18-inch peer group** — Wi-Fi browsing tops out at under two hours even with iGPU mode.

**Implication for stakeholders:** Performance and build are genuine strengths. The negative pull is two recurring themes — **AWCC software polish** and **stability under load** — each backed by multiple owners. Both are addressable; both are visible in competitor reviews and prospective-buyer threads.

---

### 2.3 MSI Cyborg 15 — competitor losing the budget tier

**54 mentions analyzed · avg net sentiment -0.386 · briefed primarily in weaknesses**

The brief surfaces no high-confidence strengths section — itself a signal.

What owners complain about:
- **GPU detection failures** — discrete GPU going completely undetected by Windows / NVIDIA drivers, leaving the system on integrated graphics.
- **45 W TGP cap on the RTX GPU** — Cyborg 15 trails even its own predecessor (RTX 4060 variant) in gaming benchmarks.
- **Chronic thermal throttling** — temperatures regularly hitting 95 °C; problem persists or worsens after repasting / fan replacement.
- **Fan vibration / whistling** — part of a broader pattern of MSI fan and vibration complaints in this segment.

**Implication for stakeholders:** MSI's entry-tier is a known soft target. The complaint set is **concrete and reproducible** (TGP cap, GPU detection, thermals) — useful both for competitive positioning and for understanding what budget-tier buyers will tolerate versus reject.

---

## 3. How it works — methodology in one page

**Sources.** Reddit (subreddit + comment), YouTube transcripts (chunked), curated review/news articles (Notebookcheck plus a few others). 5,061 mentions in `run_wave5_v1`; 96.8 % reddit by volume.

**Stack.** Local Qwen 7B for high-volume aspect tagging; Anthropic Sonnet for synthesis (brief writing); Haiku for near-duplicate dedup. No Opus in production. Deterministic LLM calls (`temperature=0`, structured JSON, versioned prompts, content-hash cached) so a re-run on the same corpus reproduces the same outputs.

**Validation.** Gold-set methodology — Sonnet-labeled, Opus-scrubbed 89-entry test set (`aspect_tagging_v2.jsonl`). Current classifier accuracy:

| Metric | Value | Notes |
|---|---|---|
| Strict micro-F1 | 0.60 | Exact match on (aspect, polarity, intensity) |
| **Loose micro-F1 (production gate)** | **0.78** | Allows ±1 intensity-bucket tolerance |

The 0.18 gap is intensity-only wobble (e.g., "high" vs "medium" thermals complaint). Loose F1 is the operational gate because intensity is a display dial, not a decision dial — the *aspect* and *polarity* are what stakeholders act on.

**Evidence-first.** Every claim in a brief cites mention IDs (typically 3 per claim). The UI renders verbatim text from the DB; the LLM never invents quotes. Brief generation includes a citation-fabrication retry: if the model cites an ID that doesn't exist in the candidate pool, the brief is regenerated against a stricter prompt.

---

## 4. Caveats — what this pilot does *not* do

- **No head-to-head deliberation analysis.** The original Wave 3 plan was to mine reddit "I'm choosing between X and Y" threads for resolved-purchase signal. The corpus was too thin (0/50 resolved in the v2 sample). Surface remains as the simpler A1-derived `/pair` aspect scorecard.
- **No verified-purchase signal yet.** BestBuy / Amazon review ingestion is not wired; reviewer authenticity is read from source-type only.
- **Notebookcheck curation deferred.** Notebookcheck mentions exist but a 28-product re-run with manufacturer-targeted scraping is queued and not yet applied. New article-source coverage will widen over the next refresh.
- **Link rot detection.** A conservative tombstone rule was shipped this session (404 / 410 / DNS-fail / refused only). A live HEAD batch on the full 5,061 corpus is in flight; 0 tombstones at the 2,000-checks mark suggest the corpus is intact.
- **MSI naming patterns** are now solid (Crosshair / Katana / Cyborg / Vector AMD-variant `A` prefix landed session 36). Future config drift in other brands' SKU naming would need similar regex tuning before a refresh.

---

## 5. Where to find this

- **Live app:** `/pulse-check` (deployed via Tailscale Funnel)
- **Repo:** `pulse-check` — full source, briefs, tests, docs
- **Refresh:** Quarterly. `scripts/refresh.py` orchestrates `scrape → tag → aggregate → brief → verify` with a dry-run-default safety gate.

*Ask the operator for read-only access to the running deployment, or for a walk-through of any spotlight SKU.*
