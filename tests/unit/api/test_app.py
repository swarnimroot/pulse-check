"""FastAPI shell tests.

Coverage priorities:
- /api/health returns 200 with a well-formed envelope
- /api/products + /api/pairs stubs return the shape the frontend will code against
- Unhandled exceptions from a route land in the generic error envelope (500)
- HTTPException passes through with the same error envelope shape
- CORS middleware emits the expected header for an allowed origin
- Frontend dist auto-mount: absent → no SPA fallback; present → index.html served
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pulse_check import __version__
from pulse_check.api.main import create_app


@pytest.fixture(autouse=True)
def _no_frontend_dist_by_default(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point ``_FRONTEND_DIST`` at a nonexistent path by default so the SPA
    catch-all doesn't shadow API or test-only routes. A real (or fake) dist
    can be re-introduced via the ``fake_frontend_dist`` fixture, which
    re-patches the same module attribute and overrides this default for
    the duration of that test.
    """
    missing = tmp_path_factory.mktemp("no_frontend_dist") / "dist"
    with patch("pulse_check.api.main._FRONTEND_DIST", missing):
        yield


def test_health_returns_ok_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert "timestamp" in body


def test_products_stub_shape() -> None:
    client = TestClient(create_app())
    response = client.get("/api/products")
    assert response.status_code == 200
    body = response.json()
    assert body == {"products": [], "note": "stub — populated in Wave 2"}


def test_pairs_stub_shape() -> None:
    client = TestClient(create_app())
    response = client.get("/api/pairs")
    assert response.status_code == 200
    body = response.json()
    assert body == {"pairs": [], "note": "stub — populated in Wave 3"}


def test_unhandled_exception_maps_to_500_envelope() -> None:
    app = create_app()

    @app.get("/_boom")
    def _boom() -> None:
        raise RuntimeError("synthetic failure")

    # raise_server_exceptions=False lets the middleware handle the error
    # rather than the TestClient re-raising it inside the test.
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
