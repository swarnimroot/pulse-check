"""Unit tests for the add_product.py CLI surface.

Covers the pure pattern-derivation + block-rendering helpers. The interactive
prompt, the live-corpus `preview_matches` (needs a DB), and the network path
are intentionally not exercised here; `append_to_yaml` is covered via a
round-trip against `load_product_set` on a tmp file.
"""

from __future__ import annotations

# scripts/ is not on the package path; load add_product as a module via importlib.
import importlib.util
from pathlib import Path

import pytest

from pulse_check.config import load_product_set

_SPEC = importlib.util.spec_from_file_location(
    "_add_product_under_test",
    Path(__file__).resolve().parents[3] / "scripts" / "add_product.py",
)
assert _SPEC is not None and _SPEC.loader is not None
add_product = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(add_product)

_DELL_URLS = [
    "https://www.dell.com/en-us/shop/dell-laptops/alienware-15-gaming-laptop/spd/alienware-da15260-gaming-laptop",
    "https://www.dell.com/en-us/shop/dell-laptops/alienware-15-gaming-laptop/spd/alienware-da15265-gaming-laptop",
]


class TestSlugify:
    def test_basic(self) -> None:
        assert add_product.slugify("Alienware 15") == "alienware_15"

    def test_punctuation_and_extra_space(self) -> None:
        assert add_product.slugify("Alienware 16  Area-51") == "alienware_16_area_51"


class TestPrimaryPattern:
    def test_two_tokens(self) -> None:
        assert add_product.name_to_primary_pattern("Alienware 15") == r"\balienware\s+15\b"

    def test_multi_token(self) -> None:
        assert (
            add_product.name_to_primary_pattern("ROG Strix G16")
            == r"\brog\s+strix\s+g16\b"
        )

    def test_no_alphanumeric_raises(self) -> None:
        with pytest.raises(SystemExit):
            add_product.name_to_primary_pattern("---")


class TestSkuSecondaryPatterns:
    def test_extracts_and_dedups(self) -> None:
        assert add_product.sku_secondary_patterns(_DELL_URLS) == [
            r"\bda15260\b",
            r"\bda15265\b",
        ]

    def test_no_sku_in_url(self) -> None:
        assert add_product.sku_secondary_patterns(["https://example.com/laptops"]) == []


class TestBuildProduct:
    def test_infers_id_and_brand(self) -> None:
        p = add_product.build_product("Alienware 15", None, None, _DELL_URLS)
        assert p.product_id == "alienware_15"
        assert p.brand == "Alienware"
        assert p.attribution_patterns.primary == [r"\balienware\s+15\b"]
        assert p.attribution_patterns.secondary == [r"\bda15260\b", r"\bda15265\b"]

    def test_explicit_brand_and_id_override(self) -> None:
        p = add_product.build_product("Some Laptop X", "AcmeCorp", "custom_id", [])
        assert p.product_id == "custom_id"
        assert p.brand == "AcmeCorp"


class TestRenderBlock:
    def test_includes_secondary_when_present(self) -> None:
        p = add_product.build_product("Alienware 15", None, None, _DELL_URLS)
        block = add_product.render_block(p)
        assert "      secondary:" in block
        assert '        - "\\\\bda15260\\\\b"' in block

    def test_omits_secondary_when_absent(self) -> None:
        p = add_product.build_product("Some Laptop X", None, None, [])
        block = add_product.render_block(p)
        assert "secondary:" not in block


class TestAppendRoundTrip:
    def test_append_then_reload(self, tmp_path: Path) -> None:
        ps = tmp_path / "ps.yaml"
        ps.write_text(
            "products:\n"
            "  - product_id: existing_one\n"
            '    display_name: "Existing One"\n'
            '    brand: "Acme"\n'
            "    aliases: []\n"
            "    attribution_patterns:\n"
            "      primary:\n"
            '        - "\\\\bexisting\\\\s+one\\\\b"\n'
            "    urls: {}\n",
            encoding="utf-8",
        )
        p = add_product.build_product("Alienware 15", None, None, _DELL_URLS)
        block = add_product.render_block(p)
        add_product.append_to_yaml(ps, block, p.product_id)

        reloaded = load_product_set(ps)
        ids = {prod.product_id for prod in reloaded.products}
        assert ids == {"existing_one", "alienware_15"}
        new = next(x for x in reloaded.products if x.product_id == "alienware_15")
        assert new.attribution_patterns.primary == [r"\balienware\s+15\b"]
        assert new.attribution_patterns.secondary == [r"\bda15260\b", r"\bda15265\b"]

    def test_invalid_block_reverts_file(self, tmp_path: Path) -> None:
        ps = tmp_path / "ps.yaml"
        original = (
            "products:\n"
            "  - product_id: existing_one\n"
            '    display_name: "Existing One"\n'
            '    brand: "Acme"\n'
            "    aliases: []\n"
            "    attribution_patterns:\n"
            "      primary:\n"
            '        - "\\\\bexisting\\\\s+one\\\\b"\n'
            "    urls: {}\n"
        )
        ps.write_text(original, encoding="utf-8")
        # Duplicate product_id -> ProductSet validator rejects on reload.
        dup_block = (
            "  - product_id: existing_one\n"
            '    display_name: "Dup"\n'
            '    brand: "Acme"\n'
            "    aliases: []\n"
            "    attribution_patterns:\n"
            "      primary:\n"
            '        - "\\\\bdup\\\\b"\n'
            "    urls: {}\n"
        )
        with pytest.raises(SystemExit):
            add_product.append_to_yaml(ps, dup_block, "existing_one")
        assert ps.read_text(encoding="utf-8") == original  # reverted
