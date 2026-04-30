"""Launch the FastAPI backend + Vite frontend dev server together.

Usage (from repo root, with the Python venv activated so `uvicorn` is on
``sys.executable``'s module path, and with frontend deps installed)::

    python scripts/serve.py                     # both servers
    python scripts/serve.py --backend-only      # just FastAPI
    python scripts/serve.py --frontend-only     # just Vite
    python scripts/serve.py --backend-port 9000 # override ports

Design notes
------------

- Processes are launched via ``subprocess.Popen`` with ``stdout`` + ``stderr``
  merged into a single pipe. A dedicated daemon thread per process prefixes
  each line (``[api]`` / ``[web]``) and flushes to the parent's stdout so the
  two streams interleave readably.
- On Windows, ``npm`` is ``npm.cmd``; resolved via ``shutil.which`` so the
  script works in bash and PowerShell alike.
- Ctrl+C (SIGINT) is caught at the top level; both children are sent
  ``terminate()`` followed by a short-fuse ``kill()`` if they don't exit.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"


def _stream_output(prefix: str, proc: subprocess.Popen[str]) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(f"{prefix} {line}")
        sys.stdout.flush()


def _launch(cmd: list[str], cwd: Path, prefix: str) -> subprocess.Popen[str]:
    print(f"{prefix} launching: {' '.join(cmd)} (cwd={cwd})", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=_stream_output, args=(prefix, proc), daemon=True).start()
    return proc


def _resolve_npm() -> str:
    """Find the npm executable. On Windows this is usually ``npm.cmd``."""
    candidate = shutil.which("npm")
    if candidate is None and os.name == "nt":
        candidate = shutil.which("npm.cmd")
    if candidate is None:
        raise SystemExit(
            "npm not found on PATH. Install Node.js 20+ LTS and reopen the shell.",
        )
    return candidate


def _backend_cmd(host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "pulse_check.api.main:app",
        "--reload",
        "--host",
        host,
        "--port",
        str(port),
    ]


def _frontend_cmd(port: int) -> list[str]:
    return [_resolve_npm(), "run", "dev", "--", "--port", str(port), "--strictPort"]


def _shutdown(procs: list[subprocess.Popen[str]]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch pulse-check dev servers.")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8765)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.backend_only and args.frontend_only:
        parser.error("--backend-only and --frontend-only are mutually exclusive")

    procs: list[subprocess.Popen[str]] = []
    try:
        if not args.frontend_only:
            procs.append(
                _launch(_backend_cmd(args.backend_host, args.backend_port), REPO_ROOT, "[api]")
            )
        if not args.backend_only:
            if not FRONTEND_DIR.exists():
                raise SystemExit(f"frontend directory not found: {FRONTEND_DIR}")
            procs.append(_launch(_frontend_cmd(args.frontend_port), FRONTEND_DIR, "[web]"))

        print("ready. press Ctrl+C to stop.", flush=True)
        while True:
            for proc in procs:
                rc = proc.poll()
                if rc is not None:
                    print(f"child exited with code {rc}; shutting down siblings", flush=True)
                    return rc or 1
            signal.pause() if hasattr(signal, "pause") else threading.Event().wait(0.5)
    except KeyboardInterrupt:
        print("\nCtrl+C received; stopping dev servers...", flush=True)
        return 0
    finally:
        _shutdown(procs)


if __name__ == "__main__":
    raise SystemExit(main())
