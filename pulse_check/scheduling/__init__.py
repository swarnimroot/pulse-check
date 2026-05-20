"""Refresh-cadence orchestration helpers.

Hosts state-file read/write + is_due() threshold logic for the quarterly
refresh skeleton (bite #6). The CLI entry point lives at
``scripts/refresh.py``; this package is the shared library it depends on.
"""
