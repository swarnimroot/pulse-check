"""FastAPI shell + handler tests.

Coverage priorities:
- /api/health returns 200 with a well-formed envelope
- /api/products returns the seeded product list
- /api/product/:id returns aspect rows + run meta or 404
- /api/mentions?ids=... returns verbatim views or empty / 400
- /api/brief/:id returns a BriefNarrative view or 404
- /api/pairs stub still returns the Wave-3 envelope
- Unhandled exceptions from a route land in the generic error envelope (500)
- HTTPException passes through with the same error envelope shape
- CORS middleware emits the expected header for an allowed origin
- Frontend dist auto-mount: absent → no SPA fallback; present → index.html served
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pulse_check import __version__
from pulse_check.api.deps import get_session
from pulse_check.api.main import create_app
from pulse_check.storage.enums import (
    Aspect,
    Intensity,
    Polarity,
    ScopeType,
    SourceType,
)
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Base,
    Brief,
    Mention,
    Product,
)


@pytest.fixture(autouse=True)
def _no_frontend_dist_by_default(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point ``_FRONTEND_DIST`` at a nonexistent path by default so the SPA
    catch-all doesn't shadow API or test-only routes.
    """
    missing = tmp_path_factory.mktemp("no_frontend_dist") / "dist"
    with patch("pulse_check.api.main._FRONTEND_DIST", missing):
        yield


@pytest.fixture
def api_engine() -> Iterator[Engine]:
    """Thread-safe in-memory SQLite engine for FastAPI handler tests.

    `StaticPool` + `check_same_thread=False` lets a single connection be shared
    between the test thread (which seeds rows via `seed_session`) and the
    starlette worker thread (which serves API requests). The conftest `engine`
    fixture isn't suitable here because TestClient runs handlers off-thread.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def seed_session(api_engine: Engine) -> Iterator[Session]:
    """Session bound to `api_engine` that tests use to insert fixtures."""
    factory = sessionmaker(bind=api_engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s


@pytest.fixture
def app_with_session(api_engine: Engine) -> Iterator[FastAPI]:
    """Build a FastAPI app whose `get_session` dependency yields sessions
    bound to `api_engine`. Per-request: commit on success, rollback on error.
    """
    app = create_app()
    factory = sessionmaker(bind=api_engine, expire_on_commit=False, future=True)

    def _override() -> Iterator[Session]:
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _seed_product(
    session: Session,
    *,
    product_id: str = "alienware_16_aurora",
    display_name: str = "Alienware 16 Aurora",
    brand: str = "Alienware",
    aliases: list[str] | None = None,
) -> Product:
    p = Product(
        product_id=product_id,
        display_name=display_name,
        brand=brand,
        aliases=aliases or [],
        attribution_patterns={},
        urls={},
    )
    session.add(p)
    session.flush()
    return p


def _seed_aggregate(
    session: Session,
    *,
    run_id: str = "smoke_test",
    product_id: str = "alienware_16_aurora",
    aspect: Aspect = Aspect.THERMALS,
    total_mentions: int = 10,
    net_sentiment: float = -0.3,
    intensity_counts: dict[str, int] | None = None,
    verified_share: float = 0.71,
    by_source: dict[str, int] | None = None,
    mention_ids: list[str] | None = None,
    total_mentions_secondary: int = 4,
    net_sentiment_secondary: float = -0.1,
    mention_ids_secondary: list[str] | None = None,
) -> AggregateAspectSku:
    agg = AggregateAspectSku(
        run_id=run_id,
        product_id=product_id,
        aspect=aspect,
        total_mentions=total_mentions,
        polarity_counts={"positive": 2, "neutral": 1, "negative": 7},
        net_sentiment=net_sentiment,
        intensity_counts=intensity_counts or {"high": 3, "medium": 5, "low": 2},
        verified_share=verified_share,
        by_source=by_source or {"reddit_post": 6, "amazon_review": 4},
        by_recency={"last_30_days": 3, "older": 7},
        mention_ids=mention_ids or [f"m{i:03d}" for i in range(total_mentions)],
        total_mentions_secondary=total_mentions_secondary,
        polarity_counts_secondary={"positive": 1, "neutral": 1, "negative": 2},
        net_sentiment_secondary=net_sentiment_secondary,
        intensity_counts_secondary={"high": 1, "medium": 2, "low": 1},
        verified_share_secondary=0.0,
        by_source_secondary={"reddit_comment": total_mentions_secondary},
        by_recency_secondary={"last_30_days": 1, "older": total_mentions_secondary - 1},
        mention_ids_secondary=mention_ids_secondary
        or [f"c{i:03d}" for i in range(total_mentions_secondary)],
        computed_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
    )
    session.add(agg)
    session.flush()
    return agg


def _seed_mention(
    session: Session,
    *,
    mention_id: str,
    source_type: SourceType = SourceType.REDDIT_POST,
    raw_text: str = "thermals are awful under load",
    metadata: dict[str, object] | None = None,
    channel: str | None = "r/GamingLaptops",
    author: str | None = "u/example",
    source_url: str = "https://reddit.com/r/example",
    published_at: datetime | None = None,
) -> Mention:
    m = Mention(
        mention_id=mention_id,
        source_type=source_type,
        source_url=source_url,
        published_at=published_at or datetime(2026, 4, 1, tzinfo=UTC),
        author=author,
        raw_text=raw_text,
        channel=channel,
        metadata_=metadata or {},
    )
    session.add(m)
    session.flush()
    return m


# ---------------------------------------------------------------------------
# Health + middleware
# ---------------------------------------------------------------------------


def test_health_returns_ok_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert "timestamp" in body


def test_unhandled_exception_maps_to_500_envelope() -> None:
    app = create_app()

    @app.get("/_boom")
    def _boom() -> None:
        raise RuntimeError("synthetic failure")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/_boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {"error": {"code": 500, "message": "internal server error"}}


def test_http_exception_envelope() -> None:
    app = create_app()

    @app.get("/_teapot")
    def _teapot() -> None:
        raise HTTPException(status_code=418, detail="i am a teapot")

    client = TestClient(app)
    response = client.get("/_teapot")
    assert response.status_code == 418
    body = response.json()
    assert body == {"error": {"code": 418, "message": "i am a teapot"}}


def test_cors_header_for_allowed_origin() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_pairs_stub_shape() -> None:
    client = TestClient(create_app())
    response = client.get("/api/pairs")
    assert response.status_code == 200
    body = response.json()
    assert body == {"pairs": [], "note": "stub — populated in Wave 3"}


# ---------------------------------------------------------------------------
# /api/products
# ---------------------------------------------------------------------------


def test_products_empty_when_no_rows(app_with_session: FastAPI) -> None:
    client = TestClient(app_with_session)
    response = client.get("/api/products")
    assert response.status_code == 200
    assert response.json() == {"products": []}


def test_products_returns_seeded_rows(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    _seed_product(
        seed_session, product_id="alienware_16_aurora", display_name="Alienware 16 Aurora"
    )
    _seed_product(
        seed_session,
        product_id="rog_strix_g16",
        display_name="ROG Strix G16",
        brand="ASUS",
        aliases=["strix_g16"],
    )
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/products").json()
    assert len(body["products"]) == 2
    # Sorted by display_name.
    assert body["products"][0]["product_id"] == "alienware_16_aurora"
    assert body["products"][1]["product_id"] == "rog_strix_g16"
    assert body["products"][1]["aliases"] == ["strix_g16"]
    assert body["products"][1]["brand"] == "ASUS"


# ---------------------------------------------------------------------------
# /api/product/:id
# ---------------------------------------------------------------------------


def test_product_detail_404_when_missing(app_with_session: FastAPI) -> None:
    client = TestClient(app_with_session)
    response = client.get("/api/product/nonexistent")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == 404


def test_product_detail_returns_aspect_rows_and_run_meta(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    _seed_product(seed_session)
    _seed_aggregate(
        seed_session,
        aspect=Aspect.THERMALS,
        total_mentions=10,
        net_sentiment=-0.42,
        mention_ids=["m000", "m001", "m002"],
        total_mentions_secondary=4,
        mention_ids_secondary=["c000", "c001"],
    )
    _seed_aggregate(
        seed_session,
        aspect=Aspect.KEYBOARD,
        total_mentions=5,
        net_sentiment=0.51,
        mention_ids=["m100", "m101"],
        total_mentions_secondary=0,
        mention_ids_secondary=[],
    )
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/product/alienware_16_aurora").json()

    assert body["product_id"] == "alienware_16_aurora"
    assert body["display_name"] == "Alienware 16 Aurora"
    assert len(body["aspects"]) == 2

    by_aspect = {row["aspect"]: row for row in body["aspects"]}
    thermals = by_aspect["thermals"]
    assert thermals["total_mentions"] == 10
    assert thermals["net_sentiment"] == -0.42
    assert thermals["intensity_counts"] == {"high": 3, "medium": 5, "low": 2}
    assert thermals["verified_pct"] == 71.0
    assert set(thermals["sources"]) == {"reddit_post", "amazon_review"}
    assert thermals["mention_ids"] == ["m000", "m001", "m002"]
    assert thermals["total_mentions_secondary"] == 4
    assert thermals["mention_ids_secondary"] == ["c000", "c001"]

    keyboard = by_aspect["keyboard"]
    assert keyboard["total_mentions_secondary"] == 0
    assert keyboard["mention_ids_secondary"] == []

    # run_meta dedupes mention_ids across PRIMARY + SECONDARY across all aspects
    # in this run; here 3+2 PRIMARY + 2 SECONDARY = 7 unique ids.
    assert body["run_meta"]["total_mentions"] == 7
    assert body["run_meta"]["window_label"] == "6-month window"

    # No A1 brief seeded for this product → field present, null.
    assert body["latest_brief_id"] is None


def test_product_detail_empty_aspects_when_no_aggregates(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    _seed_product(seed_session, product_id="legion_pro_7i", display_name="Legion Pro 7i")
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/product/legion_pro_7i").json()
    assert body["aspects"] == []
    assert body["run_meta"]["total_mentions"] == 0
    assert body["latest_brief_id"] is None


def test_product_detail_advertises_latest_a1_brief_id(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    """`latest_brief_id` is the MAX brief_id for `scope_type=aspect_1_sku` and
    `scope_id=product_id`. Briefs scoped to other products or non-A1 scopes
    must not bleed through.
    """
    _seed_product(seed_session)
    _seed_product(seed_session, product_id="rog_strix_g16", display_name="ROG Strix G16")
    _seed_aggregate(seed_session)  # so the product has a populated body
    minimal_narrative: dict[str, object] = {"brief_title": "stub", "sections": []}
    # Older A1 brief for the target product.
    older = Brief(
        run_id="smoke_test",
        scope_type=ScopeType.ASPECT_1_SKU,
        scope_id="alienware_16_aurora",
        narrative=minimal_narrative,
        prompt_version="a1_brief_v1",
        model="claude-sonnet-4-6",
    )
    # Newer A1 brief for the target product — this one must win.
    newer = Brief(
        run_id="smoke_test",
        scope_type=ScopeType.ASPECT_1_SKU,
        scope_id="alienware_16_aurora",
        narrative=minimal_narrative,
        prompt_version="a1_brief_v1",
        model="claude-sonnet-4-6",
    )
    # Different product's brief — must not leak into this product's detail.
    other = Brief(
        run_id="smoke_test",
        scope_type=ScopeType.ASPECT_1_SKU,
        scope_id="rog_strix_g16",
        narrative=minimal_narrative,
        prompt_version="a1_brief_v1",
        model="claude-sonnet-4-6",
    )
    seed_session.add_all([older, newer, other])
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/product/alienware_16_aurora").json()
    assert body["latest_brief_id"] == newer.brief_id
    assert newer.brief_id > older.brief_id  # autoincrement sanity


# ---------------------------------------------------------------------------
# /api/mentions
# ---------------------------------------------------------------------------


def test_mentions_empty_ids_returns_400(app_with_session: FastAPI) -> None:
    client = TestClient(app_with_session)
    response = client.get("/api/mentions", params={"ids": ""})
    assert response.status_code == 400


def test_mentions_oversized_batch_returns_400(app_with_session: FastAPI) -> None:
    client = TestClient(app_with_session)
    response = client.get(
        "/api/mentions",
        params={"ids": ",".join(f"m{i}" for i in range(501))},
    )
    assert response.status_code == 400


def test_mentions_returns_views_in_request_order(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    _seed_product(seed_session)
    _seed_mention(
        seed_session,
        mention_id="m001",
        source_type=SourceType.REDDIT_POST,
        raw_text="thermals are bad",
        metadata={"upvotes": 142},
    )
    _seed_mention(
        seed_session,
        mention_id="m002",
        source_type=SourceType.BESTBUY_REVIEW,
        raw_text="returned for an Asus",
        metadata={"verified_purchase": True, "rating": 2.0},
        channel="BestBuy review",
    )
    seed_session.add(
        AspectTag(
            mention_id="m002",
            product_id="alienware_16_aurora",
            aspect=Aspect.THERMALS,
            polarity=Polarity.NEGATIVE,
            intensity=Intensity.HIGH,
            taxonomy_version="v0",
            prompt_version="aspect_classifier_v1",
            model="claude-haiku-4-5-20251001",
            temperature=0.0,
        )
    )
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/mentions", params={"ids": "m002,m001"}).json()
    ids = [m["mention_id"] for m in body["mentions"]]
    assert ids == ["m002", "m001"]

    m002 = body["mentions"][0]
    assert m002["source_type"] == "bestbuy_review"
    assert m002["verified"] is True
    assert m002["rating"] == 2.0
    assert m002["upvotes"] is None
    assert len(m002["aspect_tags"]) == 1
    assert m002["aspect_tags"][0]["aspect"] == "thermals"

    m001 = body["mentions"][1]
    assert m001["source_type"] == "reddit_post"
    assert m001["upvotes"] == 142
    assert m001["rating"] is None
    assert m001["verified"] is False
    assert m001["aspect_tags"] == []


def test_mentions_drops_unknown_ids_silently(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    _seed_mention(seed_session, mention_id="m_real", raw_text="real")
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get("/api/mentions", params={"ids": "m_real,m_ghost"}).json()
    assert [m["mention_id"] for m in body["mentions"]] == ["m_real"]


# ---------------------------------------------------------------------------
# /api/brief/:id
# ---------------------------------------------------------------------------


def test_brief_404_when_missing(app_with_session: FastAPI) -> None:
    client = TestClient(app_with_session)
    response = client.get("/api/brief/9999")
    assert response.status_code == 404


def test_brief_returns_persisted_narrative(
    app_with_session: FastAPI, seed_session: Session
) -> None:
    narrative = {
        "brief_title": "Alienware 16 Aurora — A1 voice",
        "sections": [
            {
                "heading": "Strengths · review-level",
                "claims": [
                    {
                        "claim_text": "Keyboard praised across reviews.",
                        "cited_mention_ids": ["m100", "m101"],
                    }
                ],
            },
            {
                "heading": "Concerns · review-level",
                "claims": [
                    {
                        "claim_text": "α — no high-confidence concerns surfaced.",
                        "cited_mention_ids": [],
                    }
                ],
            },
        ],
        "flagged_citation_issues": {
            "is_valid": True,
            "fabricated_ids": [],
            "out_of_context_ids": [],
            "numerical_drift": [],
            "empty_claims": [],
        },
    }
    brief = Brief(
        run_id="smoke_test",
        scope_type=ScopeType.ASPECT_1_SKU,
        scope_id="alienware_16_aurora",
        narrative=narrative,
        prompt_version="a1_brief_v1",
        model="claude-sonnet-4-6",
    )
    seed_session.add(brief)
    seed_session.commit()

    client = TestClient(app_with_session)
    body = client.get(f"/api/brief/{brief.brief_id}").json()
    assert body["brief_id"] == brief.brief_id
    assert body["scope_type"] == "aspect_1_sku"
    assert body["scope_id"] == "alienware_16_aurora"
    assert body["prompt_version"] == "a1_brief_v1"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["narrative"]["brief_title"] == "Alienware 16 Aurora — A1 voice"
    assert body["narrative"]["flagged_citation_issues"]["is_valid"] is True


# ---------------------------------------------------------------------------
# Static-frontend mount behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_frontend_dist(tmp_path: Path) -> Iterator[Path]:
    """Create a minimal frontend/dist tree and patch the module-level path."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>spa</body></html>", encoding="utf-8"
    )
    (dist / "assets" / "main.js").write_text("/* test asset */", encoding="utf-8")

    with patch("pulse_check.api.main._FRONTEND_DIST", dist):
        yield dist


def test_no_dist_means_root_is_404() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 404


def test_dist_present_serves_index_html(fake_frontend_dist: Path) -> None:  # noqa: ARG001
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "spa" in response.text


def test_dist_present_serves_assets(fake_frontend_dist: Path) -> None:  # noqa: ARG001
    client = TestClient(create_app())
    response = client.get("/assets/main.js")
    assert response.status_code == 200
    assert response.text == "/* test asset */"


def test_dist_present_falls_back_to_index_for_unknown_path(
    fake_frontend_dist: Path,  # noqa: ARG001
) -> None:
    client = TestClient(create_app())
    response = client.get("/some/deep/route")
    assert response.status_code == 200
    assert "spa" in response.text


def test_dist_present_api_routes_still_work(fake_frontend_dist: Path) -> None:  # noqa: ARG001
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
