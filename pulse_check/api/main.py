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

- ``GET /api/health``   — liveness probe, returns app version + UTC timestamp.
- ``GET /api/products`` — stub; real implementation in Wave 2.
- ``GET /api/pairs``    — stub; real implementation in Wave 3.

Static SPA (only mounted when ``frontend/dist/`` exists):

- ``GET /``       — index.html (SPA entry).
- ``GET /assets/*`` — built JS / CSS / images.
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
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pulse_check import __version__
from pulse_check.settings import get_settings

log = logging.getLogger("pulse_check.api")

# Path to the built frontend, relative to the repo root. The factory checks
# this at app-build time; absent → API-only mode.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _error_payload(status_code: int, message: str, detail: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": status_code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return body


def _build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @router.get("/products")
    def list_products() -> dict[str, Any]:
        # Wave 2 will return the current run's product set (A1). For now the
        # shape is a stable envelope so the frontend can code against it.
        return {"products": [], "note": "stub — populated in Wave 2"}

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
