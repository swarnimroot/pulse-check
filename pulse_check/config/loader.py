"""YAML loaders for the three config shapes.

Public entry points:
- `load_product_set(path)` / `load_pair_plan(path)` / `load_run_config(path)`
  — parse a single YAML into its Pydantic model.
- `load_run(path)` — one-shot: loads a run config, resolves relative product_set
  and pair_plan paths against the run config's directory, parses both, and
  enforces cross-reference integrity (every product_id referenced in the pair
  plan exists in the product set).

Every failure mode — missing file, malformed YAML, schema validation error,
unknown product reference — raises `ConfigError` with a message pointing at
the offending file path.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from pulse_check.config.models import PairPlan, ProductSet, RunConfig


class ConfigError(Exception):
    """Raised for any config load / validation failure."""


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        msg = f"config file not found: {path}"
        raise ConfigError(msg)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"could not read {path}: {exc}"
        raise ConfigError(msg) from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"invalid YAML in {path}: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{path}: top-level must be a mapping, got {type(data).__name__}"
        raise ConfigError(msg)
    return data


def _parse[T: BaseModel](model_cls: type[T], data: dict[str, object], path: Path) -> T:
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        msg = f"invalid {model_cls.__name__} in {path}:\n{exc}"
        raise ConfigError(msg) from exc


def load_product_set(path: Path | str) -> ProductSet:
    p = Path(path)
    return _parse(ProductSet, _read_yaml(p), p)


def load_pair_plan(path: Path | str) -> PairPlan:
    p = Path(path)
    return _parse(PairPlan, _read_yaml(p), p)


def load_run_config(path: Path | str) -> RunConfig:
    p = Path(path)
    run = _parse(RunConfig, _read_yaml(p), p)
    base = p.parent
    product_set = run.product_set
    pair_plan = run.pair_plan
    if not product_set.is_absolute():
        product_set = (base / product_set).resolve()
    if not pair_plan.is_absolute():
        pair_plan = (base / pair_plan).resolve()
    return run.model_copy(update={"product_set": product_set, "pair_plan": pair_plan})


def load_run(path: Path | str) -> tuple[RunConfig, ProductSet, PairPlan]:
    """Load a run config and its referenced product_set + pair_plan, with
    cross-reference validation."""
    run = load_run_config(path)
    product_set = load_product_set(run.product_set)
    pair_plan = load_pair_plan(run.pair_plan)
    _validate_cross_refs(product_set, pair_plan, Path(path))
    return run, product_set, pair_plan


def _validate_cross_refs(
    product_set: ProductSet, pair_plan: PairPlan, run_config_path: Path
) -> None:
    known = product_set.product_ids()
    unknown: set[str] = set()
    for pair in pair_plan.pairs:
        if pair.primary not in known:
            unknown.add(pair.primary)
        if pair.comparator not in known:
            unknown.add(pair.comparator)
    if unknown:
        msg = (
            f"pair_plan references unknown product_id(s): {sorted(unknown)} "
            f"(run config: {run_config_path})"
        )
        raise ConfigError(msg)
