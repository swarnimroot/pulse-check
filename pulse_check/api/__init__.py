"""FastAPI backend.

v1 shell: `/health`, stubs for `/products` and `/pairs`. Real handlers land in
Waves 2 (A1) and 3 (A2). Kept as a single-module app for now; split into
`routes/` when the surface grows.
"""

from pulse_check.api.main import create_app

__all__ = ["create_app"]
