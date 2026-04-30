"""Build the frontend and run the unified FastAPI server.

This is the "share via reverse proxy" mode — single port, single process.
The same FastAPI app serves the API under ``/api/*`` and the built SPA at
every other path. Mount the resulting port behind a reverse proxy (e.g.
Tailscale Funnel) at any path; the SPA's relative asset URLs + HashRouter
make it prefix-agnostic.

Usage (from repo root)::

    python scripts/serve_public.py                # build + serve
    python scripts/serve_public.py --skip-build   # serve existing dist/
    python scripts/serve_public.py --port 8765    # override port

The dev workflow (separate Vite + uvicorn) is in ``scripts/serve.py``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"


def _resolve_npm() -> str:
    candidate = shutil.which("npm")
    if candidate is None and os.name == "nt":
        candidate = shutil.which("npm.cmd")
    if candidate is None:
        raise SystemExit(
            "npm not found on PATH. Install Node.js 20+ LTS and reopen the shell.",
        )
    return candidate


def _build_frontend() -> None:
    if not FRONTEND_DIR.exists():
        raise SystemExit(f"frontend directory not found: {FRONTEND_DIR}")
    print(f"[build] running `npm run build` in {FRONTEND_DIR}", flush=True)
    subprocess.run([_resolve_npm(), "run", "build"], cwd=str(FRONTEND_DIR), check=True)
    if not (DIST_DIR / "index.html").is_file():
        raise SystemExit(f"build completed but {DIST_DIR / 'index.html'} is missing")


def _run_uvicorn(host: str, port: int) -> int:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "pulse_check.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    print(f"[serve] {' '.join(cmd)}", flush=True)
    # Inherit stdio so the user sees uvicorn's logs directly and Ctrl+C works.
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build + serve pulse-check on a single port.")
    parser.add_argument("--skip-build", action="store_true", help="reuse existing frontend/dist/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if not args.skip_build:
        _build_frontend()
    elif not (DIST_DIR / "index.html").is_file():
        raise SystemExit(
            f"--skip-build set but {DIST_DIR / 'index.html'} is missing. "
            "Run without --skip-build first."
        )

    return _run_uvicorn(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
