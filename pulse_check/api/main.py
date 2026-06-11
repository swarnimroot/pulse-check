"""FastAPI application factory.

Two-mode app:

- **Dev mode** — Vite dev server runs separately on port 5173 and calls the
  API cross-origin. CORS allow-list (`settings.api_allowed_origins`) lets the
  dev origin through. Static-file mount is skipped because no build exists.
- **Unified prod mode** — `frontend/dist/` exists (after `npm run build`),
  so the same FastAPI process serves both the API (under ``/api/*``) and
  the static SPA (everything else). Frontend ↔ backend are same-origin so
  CORS doesn't apply.

Routes (all under ``/api`` prefix):

- ``GET /api/health``                  — liveness probe.
- ``GET /api/products``                — product set in the latest run.
- ``GET /api/product/{product_id}``    — product detail + per-aspect aggregate rows.
- ``GET /api/mentions?ids=<csv>``      — verbatim cards by mention-id list.
- ``GET /api/brief/{brief_id}``        — persisted §6.3 brief narrative.
- ``GET /api/trend/{product_id}``      — per-aspect sentiment/volume across snapshots.
- ``GET /api/pairs``                   — stub; A2 ships in Wave 3.

Static SPA (only mounted when ``frontend/dist/`` exists):

- ``GET /``                — index.html (SPA entry).
- ``GET /assets/*``        — built JS / CSS / images.
- ``GET /<anything-else>`` — falls back to index.html so direct deep links work.

The path-prefix the SPA lives at on the public URL (e.g. ``/pulse-check`` via
Tailscale Funnel) is stripped by the reverse proxy before requests reach this
app, so the app itself stays prefix-agnostic — a rename on the proxy side
needs no code change.

ASGI entry point for uvicorn is :data:`app` at module scope.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulse_check import __version__
from pulse_check.api.deps import get_session
from pulse_check.api.schemas import (
    AspectRow,
    BriefView,
    CompareCell,
    CompareProductRow,
    CompareResponse,
    HomeSummary,
    MentionsResponse,
    MentionView,
    PairAspectCell,
    PairAspectRow,
    PairProductRef,
    PairResponse,
    PipelineStageStat,
    ProductDetail,
    ProductsResponse,
    ProductSummary,
    RunMeta,
    SourceEntry,
    SourcesResponse,
    TrendAspectPoint,
    TrendResponse,
    TrendSnapshot,
)
from pulse_check.config.loader import ConfigError, load_rss_sources, load_run_config
from pulse_check.scheduling.weekly_snapshot import is_weekly_run_id
from pulse_check.settings import get_settings
from pulse_check.storage.enums import Aspect, ContentType, ScopeType
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Brief,
    ContentTypeTag,
    Mention,
    Product,
)

# Imported from the submodule (not the `tagging` package) so the API doesn't
# pull in OllamaClient et al. — these are just the version strings the Stage-B
# aggregator tags with (see a1.aggregate_a1).
from pulse_check.tagging.aspect_classifier import (
    PROMPT_VERSION as ASPECT_PROMPT_VERSION,
)
from pulse_check.tagging.aspect_classifier import (
    TAXONOMY_VERSION as ASPECT_TAXONOMY_VERSION,
)

# Source-config paths read by `/api/sources`. Operator-curated YAMLs in
# `configs/`; resolved relative to the repo root (the parent of `pulse_check/`).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUN_CONFIG_PATH = _REPO_ROOT / "configs" / "run_wave5_v1.yaml"
_RSS_SOURCES_PATH = _REPO_ROOT / "configs" / "wave5_rss_sources.yaml"

# Net-sentiment delta below this threshold (in absolute value) is treated as a
# tie in the head-to-head view rather than a lead. 0.10 maps to ~5 % of the
# full [-1, +1] range — meaningful gap, not noise.
_PAIR_LEAD_THRESHOLD = 0.10

# Max mention_ids returned per heatmap cell. The EvidenceDrawer only needs
# enough to populate the drill; the full list is on /api/product/:id if a
# caller wants everything.
_COMPARE_MENTION_CAP = 50

# FastAPI dependency-injection alias — used in handler signatures so ruff B008
# (no function calls in argument defaults) doesn't trip on `Depends(...)` while
# we keep the standard FastAPI pattern.
SessionDep = Annotated[Session, Depends(get_session)]

log = logging.getLogger("pulse_check.api")

# Path to the built frontend, relative to the repo root. The factory checks
# this at app-build time; absent → API-only mode.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Window label is hardcoded for v1; cohort toggles are hidden per session-13
# locks, and the scrape window is documented in run config rather than the
# `runs` row (which is empty in the live DB — see SESSION_LOG open item).
_WINDOW_LABEL = "6-month window"


def _error_payload(status_code: int, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": status_code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return body


def _aggregate_to_row(agg: AggregateAspectSku) -> AspectRow:
    by_source = agg.by_source or {}
    by_source_secondary = agg.by_source_secondary or {}
    return AspectRow(
        aspect=agg.aspect.value,
        total_mentions=agg.total_mentions,
        net_sentiment=agg.net_sentiment,
        intensity_counts=dict(agg.intensity_counts or {}),
        verified_pct=round(agg.verified_share * 100, 1),
        sources=list(by_source.keys()),
        mention_ids=list(agg.mention_ids or []),
        total_mentions_secondary=agg.total_mentions_secondary,
        net_sentiment_secondary=agg.net_sentiment_secondary,
        intensity_counts_secondary=dict(agg.intensity_counts_secondary or {}),
        verified_pct_secondary=round(agg.verified_share_secondary * 100, 1),
        sources_secondary=list(by_source_secondary.keys()),
        mention_ids_secondary=list(agg.mention_ids_secondary or []),
    )


def _latest_run_id_overall(session: Session) -> str | None:
    """Most-recent run_id across all products by aggregate `computed_at`.

    Used by `/api/compare` when the caller doesn't specify `?run_id=`. Mirrors
    the picking strategy of `_latest_run_id_for_product` so the two endpoints
    stay consistent.
    """
    stmt = (
        select(AggregateAspectSku.run_id)
        .order_by(AggregateAspectSku.computed_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _latest_run_id_for_product(session: Session, product_id: str) -> str | None:
    """Most-recent run_id for which this product has aggregate rows.

    Avoids relying on the `runs` table (empty in the live DB) — picks the run
    based on `aggregates_aspect_sku.computed_at` instead.
    """
    stmt = (
        select(AggregateAspectSku.run_id)
        .where(AggregateAspectSku.product_id == product_id)
        .order_by(AggregateAspectSku.computed_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _latest_a1_brief_id_for_product(session: Session, product_id: str) -> int | None:
    """Highest `brief_id` for an A1 (per-product) brief scoped to this product.

    Lets `/api/product/{id}` advertise the brief link inline so the Standalone
    page navigates product → brief in one hop.
    """
    stmt = (
        select(Brief.brief_id)
        .where(
            Brief.scope_type == ScopeType.ASPECT_1_SKU,
            Brief.scope_id == product_id,
        )
        .order_by(Brief.brief_id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _latest_pair_brief_id(
    session: Session, primary: str, competitor: str
) -> int | None:
    """Highest `brief_id` for a pair brief scoped to this directed pair.

    Convention: `scope_id == f"{primary}_vs_{competitor}"`, matching the
    `pair_id` shape from `configs/pair_plan_*.yaml` and the orchestrator's
    `synthesize_pair` call site. Lets `/api/pair` advertise the brief link
    inline so the Pair page navigates pair → brief in one hop.
    """
    pair_id = f"{primary}_vs_{competitor}"
    stmt = (
        select(Brief.brief_id)
        .where(
            Brief.scope_type == ScopeType.ASPECT_2_PAIR,
            Brief.scope_id == pair_id,
        )
        .order_by(Brief.brief_id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _is_retailer_review(source_type: str) -> bool:
    return source_type in {"bestbuy_review", "amazon_review"}


def _is_reddit(source_type: str) -> bool:
    return source_type in {"reddit_post", "reddit_comment"}


def _mention_to_view(mention: Mention, tags: list[AspectTag]) -> MentionView:
    metadata = mention.metadata_ or {}
    source_type = mention.source_type.value
    upvotes_raw = metadata.get("upvotes") if _is_reddit(source_type) else None
    rating_raw = metadata.get("rating") if _is_retailer_review(source_type) else None
    # Canonical aspect order (Aspect enum declaration order) so `aspect_tags[0]`
    # is deterministic for any consumer that reads the "first" tag without an
    # explicit focus aspect (e.g. pooled CitationPanel cards). Within an aspect,
    # break ties by product_id so multi-product mentions stay stable too.
    aspect_order = {a: i for i, a in enumerate(Aspect)}
    ordered_tags = sorted(
        tags, key=lambda t: (aspect_order.get(t.aspect, len(aspect_order)), t.product_id)
    )
    return MentionView(
        mention_id=mention.mention_id,
        source_type=source_type,
        channel=mention.channel,
        author=mention.author,
        published_at=mention.published_at,
        raw_text=mention.raw_text,
        url=mention.source_url,
        verified=bool(metadata.get("verified_purchase", False)),
        upvotes=int(upvotes_raw) if isinstance(upvotes_raw, (int, float)) else None,
        rating=float(rating_raw) if isinstance(rating_raw, (int, float)) else None,
        aspect_tags=[
            {
                "aspect": t.aspect.value,
                "polarity": t.polarity.value,
                "intensity": t.intensity.value,
                "product_id": t.product_id,
            }
            for t in ordered_tags
        ],
        tombstoned_at=mention.tombstoned_at,
        tombstone_reason=mention.tombstone_reason,
    )


def _build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @router.get("/products", response_model=ProductsResponse)
    def list_products(session: SessionDep) -> ProductsResponse:
        rows = session.execute(select(Product).order_by(Product.display_name)).scalars().all()
        return ProductsResponse(
            products=[
                ProductSummary(
                    product_id=p.product_id,
                    display_name=p.display_name,
                    brand=p.brand,
                    aliases=list(p.aliases or []),
                )
                for p in rows
            ]
        )

    @router.get("/product/{product_id}", response_model=ProductDetail)
    def get_product(
        product_id: str,
        session: SessionDep,
    ) -> ProductDetail:
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"product not found: {product_id}")

        run_id = _latest_run_id_for_product(session, product_id)
        latest_brief_id = _latest_a1_brief_id_for_product(session, product_id)
        if run_id is None:
            # Product exists but has no aggregate rows yet — return shell with empty aspects.
            return ProductDetail(
                product_id=product.product_id,
                display_name=product.display_name,
                brand=product.brand,
                aliases=list(product.aliases or []),
                aspects=[],
                run_meta=RunMeta(
                    total_mentions=0,
                    window_label=_WINDOW_LABEL,
                    last_refreshed=datetime.now(UTC),
                ),
                latest_brief_id=latest_brief_id,
            )

        stmt = (
            select(AggregateAspectSku)
            .where(
                AggregateAspectSku.product_id == product_id,
                AggregateAspectSku.run_id == run_id,
            )
            .order_by(AggregateAspectSku.aspect)
        )
        aggregates = list(session.execute(stmt).scalars().all())

        unique_mention_ids: set[str] = set()
        latest_computed_at = datetime.now(UTC)
        rows: list[AspectRow] = []
        for agg in aggregates:
            unique_mention_ids.update(agg.mention_ids or [])
            unique_mention_ids.update(agg.mention_ids_secondary or [])
            if agg.computed_at and agg.computed_at > latest_computed_at:
                latest_computed_at = agg.computed_at
            rows.append(_aggregate_to_row(agg))

        # Take the max computed_at (or now if all rows had future timestamps somehow).
        if aggregates:
            latest_computed_at = max(a.computed_at for a in aggregates if a.computed_at)

        return ProductDetail(
            product_id=product.product_id,
            display_name=product.display_name,
            brand=product.brand,
            aliases=list(product.aliases or []),
            aspects=rows,
            run_meta=RunMeta(
                total_mentions=len(unique_mention_ids),
                window_label=_WINDOW_LABEL,
                last_refreshed=latest_computed_at,
            ),
            latest_brief_id=latest_brief_id,
        )

    @router.get("/trend/{product_id}", response_model=TrendResponse)
    def get_trend(
        product_id: str,
        session: SessionDep,
    ) -> TrendResponse:
        """Per-aspect net-sentiment / volume time series across snapshots.

        Each distinct ``run_id`` with aggregate rows for this product is one
        point on the time axis — the pilot run plus each weekly snapshot from
        ``scripts/weekly_analyze.py`` (daily-ingestion cadence, step 4).
        Snapshots are returned oldest-first by ``computed_at``. No UI consumes
        this yet; the read path ships ahead of the chart.
        """
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"product not found: {product_id}")

        rows = list(
            session.execute(
                select(AggregateAspectSku)
                .where(AggregateAspectSku.product_id == product_id)
                .order_by(AggregateAspectSku.run_id, AggregateAspectSku.aspect)
            )
            .scalars()
            .all()
        )

        aspect_order = {a: i for i, a in enumerate(Aspect)}
        by_run: dict[str, list[AggregateAspectSku]] = {}
        for agg in rows:
            # Trend axis = weekly snapshots only. The pilot run (wave5_v1) and
            # ad-hoc ids (smoke_test) carry aggregate rows too, but they aren't
            # part of the week-over-week cadence and would pollute the chart.
            if not is_weekly_run_id(agg.run_id):
                continue
            by_run.setdefault(agg.run_id, []).append(agg)

        snapshots: list[TrendSnapshot] = []
        for run_id, aggs in by_run.items():
            computed_at = max(
                (a.computed_at for a in aggs if a.computed_at),
                default=datetime.now(UTC),
            )
            points = [
                TrendAspectPoint(
                    aspect=a.aspect.value,
                    total_mentions=a.total_mentions,
                    net_sentiment=a.net_sentiment,
                )
                for a in sorted(
                    aggs,
                    key=lambda x: aspect_order.get(x.aspect, len(aspect_order)),
                )
            ]
            snapshots.append(
                TrendSnapshot(run_id=run_id, computed_at=computed_at, aspects=points)
            )

        # Oldest first; run_id breaks ties when two snapshots share a timestamp.
        snapshots.sort(key=lambda s: (s.computed_at, s.run_id))

        return TrendResponse(
            product_id=product.product_id,
            display_name=product.display_name,
            snapshots=snapshots,
            generated_at=datetime.now(UTC),
        )

    @router.get("/mentions", response_model=MentionsResponse)
    def get_mentions(
        session: SessionDep,
        ids: Annotated[str, Query(description="Comma-separated mention_id list.")],
    ) -> MentionsResponse:
        mention_ids = [s.strip() for s in ids.split(",") if s.strip()]
        if not mention_ids:
            raise HTTPException(status_code=400, detail="ids parameter is empty")

        # Cap the batch size to keep the query bounded.
        if len(mention_ids) > 500:
            raise HTTPException(status_code=400, detail="ids parameter exceeds 500 entries")

        mentions = list(
            session.execute(
                select(Mention).where(Mention.mention_id.in_(mention_ids))
            ).scalars()
        )
        # Preserve caller-provided order; drop unknown ids silently (deleted/tombstoned).
        by_id = {m.mention_id: m for m in mentions}
        ordered = [by_id[mid] for mid in mention_ids if mid in by_id]

        if not ordered:
            return MentionsResponse(mentions=[])

        # Filter to the current tag version so the drawer chip matches the
        # heatmap cell. The cell's net_sentiment is aggregated from this exact
        # (taxonomy_version, prompt_version) pair (a1.aggregate_a1); returning
        # all versions would let a future re-tagging pass surface a stale-version
        # tag whose polarity disagrees with the cell colour.
        tags_stmt = select(AspectTag).where(
            AspectTag.mention_id.in_([m.mention_id for m in ordered]),
            AspectTag.taxonomy_version == ASPECT_TAXONOMY_VERSION,
            AspectTag.prompt_version == ASPECT_PROMPT_VERSION,
        )
        tags_by_mention: dict[str, list[AspectTag]] = {}
        for tag in session.execute(tags_stmt).scalars():
            tags_by_mention.setdefault(tag.mention_id, []).append(tag)

        return MentionsResponse(
            mentions=[
                _mention_to_view(m, tags_by_mention.get(m.mention_id, []))
                for m in ordered
            ]
        )

    @router.get("/brief/{brief_id}", response_model=BriefView)
    def get_brief(
        brief_id: int,
        session: SessionDep,
    ) -> BriefView:
        brief = session.get(Brief, brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail=f"brief not found: {brief_id}")
        return BriefView(
            brief_id=brief.brief_id,
            run_id=brief.run_id,
            scope_type=brief.scope_type.value,
            scope_id=brief.scope_id,
            prompt_version=brief.prompt_version,
            model=brief.model,
            generated_at=brief.generated_at,
            narrative=dict(brief.narrative or {}),
        )

    @router.get("/compare", response_model=CompareResponse)
    def get_compare(
        session: SessionDep,
        run_id: Annotated[
            str | None,
            Query(description="Run to render. Defaults to the latest run with any data."),
        ] = None,
    ) -> CompareResponse:
        """Cross-product heatmap payload (all 59 products × ≤11 aspects).

        Sparse: cells with zero mentions are omitted (frontend renders an
        empty cell against the canonical aspect column order). Alienware
        products are sorted first per manufacturer POV; remaining brands
        alphabetical by brand then display name.
        """
        chosen_run_id = run_id or _latest_run_id_overall(session)

        aggregates: list[AggregateAspectSku] = []
        if chosen_run_id is not None:
            aggregates = list(
                session.execute(
                    select(AggregateAspectSku).where(
                        AggregateAspectSku.run_id == chosen_run_id
                    )
                ).scalars()
            )

        by_product: dict[str, list[AggregateAspectSku]] = {}
        for agg in aggregates:
            by_product.setdefault(agg.product_id, []).append(agg)

        products = list(
            session.execute(select(Product)).scalars()
        )
        # Alienware first (any brand whose name starts with "Alienware"), then
        # brands alphabetically, then display name within brand.
        def _sort_key(p: Product) -> tuple[int, str, str]:
            is_alienware = 0 if p.brand.lower().startswith("alienware") else 1
            return (is_alienware, p.brand.lower(), p.display_name.lower())

        products.sort(key=_sort_key)

        rows: list[CompareProductRow] = []
        for p in products:
            cells: list[CompareCell] = []
            for agg in by_product.get(p.product_id, []):
                if agg.total_mentions <= 0:
                    continue
                ids = list(agg.mention_ids or [])[:_COMPARE_MENTION_CAP]
                cells.append(
                    CompareCell(
                        aspect=agg.aspect.value,
                        total_mentions=agg.total_mentions,
                        net_sentiment=agg.net_sentiment,
                        mention_ids=ids,
                    )
                )
            rows.append(
                CompareProductRow(
                    product_id=p.product_id,
                    display_name=p.display_name,
                    brand=p.brand,
                    cells=cells,
                )
            )

        return CompareResponse(
            products=rows,
            aspects=[a.value for a in Aspect],
            run_id=chosen_run_id,
            generated_at=datetime.now(UTC),
        )

    @router.get("/home", response_model=HomeSummary)
    def get_home(session: SessionDep) -> HomeSummary:
        """Home page summary + plain-English pipeline explainer (bite 32.b).

        Returns the run identifier, headline metrics for the metadata strip,
        and a sequence of pipeline stage cards with live counts. Numbers
        reflect the chosen run (the latest run with any aggregate rows).
        """
        run_id = _latest_run_id_overall(session)

        total_mentions = session.execute(
            select(func.count(Mention.mention_id))
        ).scalar_one()
        source_count = session.execute(
            select(func.count(func.distinct(Mention.source_type)))
        ).scalar_one()
        deal_count = session.execute(
            select(func.count(ContentTypeTag.mention_id)).where(
                ContentTypeTag.content_type == ContentType.DEAL
            )
        ).scalar_one()
        eligible_count = max(total_mentions - deal_count, 0)

        aspect_tag_count = session.execute(
            select(func.count(AspectTag.tag_id))
        ).scalar_one()
        tagged_distinct_mentions = session.execute(
            select(func.count(func.distinct(AspectTag.mention_id)))
        ).scalar_one()
        coverage_pct = (
            round(100.0 * tagged_distinct_mentions / eligible_count, 1)
            if eligible_count
            else 0.0
        )

        products_tracked = 0
        agg_count = 0
        brief_count = 0
        if run_id is not None:
            products_tracked = (
                session.execute(
                    select(
                        func.count(func.distinct(AggregateAspectSku.product_id))
                    ).where(AggregateAspectSku.run_id == run_id)
                ).scalar_one()
            )
            agg_count = session.execute(
                select(func.count(AggregateAspectSku.aggregate_id)).where(
                    AggregateAspectSku.run_id == run_id
                )
            ).scalar_one()
            brief_count = session.execute(
                select(func.count(Brief.brief_id)).where(Brief.run_id == run_id)
            ).scalar_one()

        pipeline: list[PipelineStageStat] = [
            PipelineStageStat(
                key="pull",
                label="PULL",
                title="Gather mentions",
                description=(
                    "Pulls every public mention of the tracked products — Reddit "
                    "threads, editorial articles, and other public sources — "
                    "looking back six months."
                ),
                chips=[
                    {"name": "mentions", "value": total_mentions},
                    {"name": "sources", "value": source_count},
                ],
            ),
            PipelineStageStat(
                key="narrow",
                label="NARROW",
                title="Filter out the noise",
                description=(
                    "Drops obvious price-and-deal chatter so the rest is genuine "
                    "opinion, not coupon traffic."
                ),
                chips=[
                    {"name": "in", "value": total_mentions},
                    {"name": "kept", "value": eligible_count},
                ],
            ),
            PipelineStageStat(
                key="tag",
                label="TAG",
                title="Read each mention",
                description=(
                    "An AI reader skims every mention and tags what it's about "
                    "(thermals, keyboard, battery, …) and how strongly the person "
                    "feels."
                ),
                ai=True,
                chips=[
                    {"name": "tags", "value": aspect_tag_count},
                    {"name": "coverage", "value": f"{coverage_pct}%"},
                ],
            ),
            PipelineStageStat(
                key="score",
                label="SCORE",
                title="Roll up by product",
                description=(
                    "Counts the tags per product and per aspect, so every product "
                    "gets an at-a-glance scorecard."
                ),
                chips=[
                    {"name": "scorecards", "value": agg_count},
                    {"name": "products", "value": products_tracked},
                ],
            ),
            PipelineStageStat(
                key="narrate",
                label="NARRATE",
                title="Write the brief",
                description=(
                    "A second AI summarizes the scorecard into plain-English bullets, "
                    "citing the original quotes so every claim is traceable."
                ),
                ai=True,
                chips=[
                    {"name": "briefs", "value": brief_count},
                ],
            ),
        ]

        return HomeSummary(
            run_id=run_id,
            products_tracked=products_tracked,
            mentions_analyzed=total_mentions,
            pipeline=pipeline,
            generated_at=datetime.now(UTC),
        )

    @router.get("/pair", response_model=PairResponse)
    def get_pair(
        session: SessionDep,
        primary: Annotated[str, Query(description="Primary product_id.")],
        competitor: Annotated[str, Query(description="Competitor product_id.")],
        run_id: Annotated[
            str | None,
            Query(description="Run to render. Defaults to the latest run."),
        ] = None,
    ) -> PairResponse:
        """Head-to-head aspect scorecard for two products under one run.

        Returns 11 aspect rows in canonical order. Each row carries both
        products' cells (or `None` if either product had zero qualifying
        mentions for that aspect), plus the net-sentiment delta and a stable
        `leader` string. Summary counts at the top let the frontend render
        the "leads on N of 11" headline without re-deriving the comparison.
        """
        if primary == competitor:
            raise HTTPException(
                status_code=400,
                detail="primary and competitor must differ",
            )
        prim_p = session.get(Product, primary)
        comp_p = session.get(Product, competitor)
        if prim_p is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown product_id: {primary}",
            )
        if comp_p is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown product_id: {competitor}",
            )

        chosen_run_id = run_id or _latest_run_id_overall(session)

        aggregates: list[AggregateAspectSku] = []
        if chosen_run_id is not None:
            aggregates = list(
                session.execute(
                    select(AggregateAspectSku).where(
                        AggregateAspectSku.run_id == chosen_run_id,
                        AggregateAspectSku.product_id.in_(
                            [primary, competitor]
                        ),
                    )
                ).scalars()
            )

        by_key: dict[tuple[str, str], AggregateAspectSku] = {
            (agg.product_id, agg.aspect.value): agg for agg in aggregates
        }

        def _cell(agg: AggregateAspectSku | None) -> PairAspectCell | None:
            if agg is None or agg.total_mentions <= 0:
                return None
            return PairAspectCell(
                total_mentions=agg.total_mentions,
                net_sentiment=agg.net_sentiment,
                mention_ids=list(agg.mention_ids or [])[:_COMPARE_MENTION_CAP],
            )

        rows: list[PairAspectRow] = []
        primary_leads = 0
        competitor_leads = 0
        ties = 0
        for aspect in Aspect:
            p_cell = _cell(by_key.get((primary, aspect.value)))
            c_cell = _cell(by_key.get((competitor, aspect.value)))

            if p_cell is None and c_cell is None:
                delta = 0.0
                leader = "tie"
                ties += 1
            elif p_cell is None:
                # Only competitor has data — count as a competitor lead.
                delta = -1.0
                leader = "competitor"
                competitor_leads += 1
            elif c_cell is None:
                delta = 1.0
                leader = "primary"
                primary_leads += 1
            else:
                delta = p_cell.net_sentiment - c_cell.net_sentiment
                if delta > _PAIR_LEAD_THRESHOLD:
                    leader = "primary"
                    primary_leads += 1
                elif delta < -_PAIR_LEAD_THRESHOLD:
                    leader = "competitor"
                    competitor_leads += 1
                else:
                    leader = "tie"
                    ties += 1

            rows.append(
                PairAspectRow(
                    aspect=aspect.value,
                    primary=p_cell,
                    competitor=c_cell,
                    delta=delta,
                    leader=leader,
                )
            )

        return PairResponse(
            primary=PairProductRef(
                product_id=prim_p.product_id,
                display_name=prim_p.display_name,
                brand=prim_p.brand,
            ),
            competitor=PairProductRef(
                product_id=comp_p.product_id,
                display_name=comp_p.display_name,
                brand=comp_p.brand,
            ),
            aspects=[a.value for a in Aspect],
            rows=rows,
            primary_leads_count=primary_leads,
            competitor_leads_count=competitor_leads,
            ties_count=ties,
            run_id=chosen_run_id,
            generated_at=datetime.now(UTC),
            latest_pair_brief_id=_latest_pair_brief_id(session, primary, competitor),
        )

    @router.get("/sources", response_model=SourcesResponse)
    def get_sources() -> SourcesResponse:
        """Operator-curated source list for the active run (bite 32.c).

        Reads `configs/run_wave5_v1.yaml` for the Reddit subreddit set and
        `configs/wave5_rss_sources.yaml` for YouTube channels + article RSS
        feeds at request time. Returns a structured payload the home page
        renders as a three-column table inside the "Under the hood"
        accordion. Disabled article feeds (`enabled: false` in YAML) are
        filtered out.
        """
        reddit: list[SourceEntry] = []
        youtube: list[SourceEntry] = []
        review_sites: list[SourceEntry] = []

        try:
            run = load_run_config(_RUN_CONFIG_PATH)
        except ConfigError as exc:
            raise HTTPException(
                status_code=500, detail=f"could not load run config: {exc}"
            ) from exc

        reddit_window = run.source_windows.reddit
        if reddit_window is not None:
            for sub in reddit_window.subreddits:
                reddit.append(
                    SourceEntry(name=f"r/{sub}", detail=f"reddit.com/r/{sub}")
                )

        try:
            rss = load_rss_sources(_RSS_SOURCES_PATH)
        except ConfigError as exc:
            raise HTTPException(
                status_code=500, detail=f"could not load rss sources: {exc}"
            ) from exc

        for ch in rss.youtube_channels:
            youtube.append(
                SourceEntry(name=ch.display_name, detail=ch.handle)
            )
        for feed in rss.article_rss_feeds:
            if not feed.enabled:
                continue
            review_sites.append(
                SourceEntry(name=feed.site, detail=feed.rss_url)
            )

        return SourcesResponse(
            reddit=reddit,
            youtube=youtube,
            review_sites=review_sites,
            generated_at=datetime.now(UTC),
        )

    @router.get("/pairs")
    def list_pairs() -> dict[str, Any]:
        # Wave 3 will return the pair plan (A2). Same envelope convention.
        return {"pairs": [], "note": "stub — populated in Wave 3"}

    return router


def _attach_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Mount the built SPA. Asset requests served from disk; other GETs fall
    back to ``index.html`` so client-side routes (HashRouter or BrowserRouter)
    resolve. Only mounts if ``dist_dir/index.html`` exists.
    """
    index_html = dist_dir / "index.html"
    if not index_html.is_file():
        log.info("frontend dist not found at %s; running API-only", dist_dir)
        return

    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
        # Any GET that isn't /api/* or /assets/* lands here and gets index.html.
        # The frontend's client-side router takes over from there.
        return FileResponse(index_html)


def create_app() -> FastAPI:
    """Build the FastAPI app with middleware + routes wired in.

    Factory form so tests can construct a fresh app per case if needed, and so
    settings are read at app-build time rather than import time.
    """
    settings = get_settings()

    app = FastAPI(
        title="pulse-check",
        version=__version__,
        description="Product-listening pilot engine — backend API.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.status_code, exc.detail or "http error"),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log with traceback; return a sanitized envelope to the client.
        log.exception("unhandled exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload(500, "internal server error"),
        )

    app.include_router(_build_api_router())
    _attach_frontend(app, _FRONTEND_DIST)

    return app


app = create_app()
