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
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check import __version__
from pulse_check.api.deps import get_session
from pulse_check.api.schemas import (
    AspectRow,
    BriefView,
    MentionsResponse,
    MentionView,
    ProductDetail,
    ProductsResponse,
    ProductSummary,
    RunMeta,
)
from pulse_check.settings import get_settings
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Brief,
    Mention,
    Product,
)

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


def _is_retailer_review(source_type: str) -> bool:
    return source_type in {"bestbuy_review", "amazon_review"}


def _is_reddit(source_type: str) -> bool:
    return source_type in {"reddit_post", "reddit_comment"}


def _mention_to_view(mention: Mention, tags: list[AspectTag]) -> MentionView:
    metadata = mention.metadata_ or {}
    source_type = mention.source_type.value
    upvotes_raw = metadata.get("upvotes") if _is_reddit(source_type) else None
    rating_raw = metadata.get("rating") if _is_retailer_review(source_type) else None
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
            for t in tags
        ],
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

        tags_stmt = select(AspectTag).where(
            AspectTag.mention_id.in_([m.mention_id for m in ordered])
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
