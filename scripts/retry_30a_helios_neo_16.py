"""One-off: retry the acer_predator_helios_neo_16 Notebookcheck article fetch.

Session 30 bite 30.a. The session-29 full Wave 5 scrape lost 1/33 NBC URLs to
a Cloudflare backoff on this specific request; backoff has since expired.
Targeted retry through the same `_enqueue_discovered_urls` path, with reddit
and rss windows disabled and an isolated scheduler state file so no stale
queue rows from session 29 fire alongside.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pulse_check.config import load_run
from pulse_check.logging_config import configure_logging
from pulse_check.scraping.discovered_urls import load_approved_discovered_urls
from pulse_check.scraping.orchestrator import run_scrape
from pulse_check.storage.session import session_scope

log = logging.getLogger("pulse_check.scripts.retry_30a_helios_neo_16")

PRODUCT_ID = "acer_predator_helios_neo_16"
RUN_CONFIG_PATH = Path("configs/run_wave5_v1.yaml")
DISCOVERED_DIR = Path("data/discovered_urls/notebookcheck")
ISOLATED_STATE = Path("data/scheduler_state_30a_retry.sqlite")


def main() -> int:
    configure_logging()

    run_config, product_set, _pair_plan, _rss_sources = load_run(RUN_CONFIG_PATH)

    all_entries = load_approved_discovered_urls(DISCOVERED_DIR)
    filtered_entries = [e for e in all_entries if e.product_id == PRODUCT_ID]
    if not filtered_entries:
        print(f"no discovered URLs for {PRODUCT_ID}")
        return 1

    print(f"retrying {len(filtered_entries)} URL(s) for {PRODUCT_ID}:")
    for e in filtered_entries:
        print(f"  - {e.url}")
    print()

    if run_config.source_windows.reddit is not None:
        run_config.source_windows.reddit.enabled = False
    if run_config.source_windows.rss is not None:
        run_config.source_windows.rss.enabled = False

    if ISOLATED_STATE.exists():
        ISOLATED_STATE.unlink()

    with session_scope() as session:
        ingest, secondary, inheritance = run_scrape(
            session,
            run_config,
            product_set,
            rss_sources=None,
            discovered_urls=filtered_entries,
            state_file=ISOLATED_STATE,
        )

    print()
    print("result:")
    print(f"  mentions:     new={ingest.new_mentions} existing={ingest.existing_mentions}")
    print(
        f"  attributions: primary={ingest.new_attributions} "
        f"secondary={secondary.new_attributions} "
        f"inherited={inheritance.new_attributions}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
