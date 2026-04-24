"""
Regression tests for the DRS items ingestion pipeline (P2 in the v0.2 roadmap).

Three layers are exercised:

1. The MediaWiki wikitable parser (`parse_drs_table`) on a hand-authored
   fixture mimicking the bg3.wiki/wiki/Damage_Mechanics tables.
2. The SQLite schema / round-trip (`SpellDB.upsert_drs_item`,
   `SpellDB.list_drs_items`).
3. The Python ↔ Lean drift check: `dataset/drs_items_seed.json` is the
   single source of truth, and `src/2_fv_core/Axioms/DRSItems.lean` must
   be byte-identical to what `drs_lean_export.py` would produce.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from auto_formalizer.database import SpellDB
from auto_formalizer.drs_lean_export import (
    DEFAULT_JSON,
    DEFAULT_LEAN,
    render_lean,
)
from auto_formalizer.models import DamageLayerKind, DamageType, DRSItem
from auto_formalizer.wikitext_parser import (
    _split_wikitable_rows,
    _strip_link_to_name,
    parse_drs_table,
)


# ── Wikitext helpers ────────────────────────────────────────────────────────


class TestSplitWikitableRows:
    def test_basic_pipe_table(self) -> None:
        body = textwrap.dedent(
            """
            |-
            ! Item !! Tier !! Description
            |-
            | Foo || One || A simple foo
            |-
            | Bar || Two || A trickier bar
            """
        ).strip()
        rows = _split_wikitable_rows(body)
        # Two data rows, headers dropped.
        assert len(rows) == 2
        assert rows[0][0] == "Foo"
        assert rows[1][0] == "Bar"

    def test_multiline_cell(self) -> None:
        body = textwrap.dedent(
            """
            |-
            ! Item !! Notes
            |-
            | Lightning Jabber
            | 1d4 Lightning, treated as Source
            """
        ).strip()
        rows = _split_wikitable_rows(body)
        assert len(rows) == 1
        # Multi-line cells become separate entries (continuation pipes).
        assert rows[0][0] == "Lightning Jabber"
        assert any("Lightning" in c for c in rows[0])


class TestStripLinkToName:
    def test_simple_link(self) -> None:
        assert _strip_link_to_name("[[Lightning Jabber]]") == "Lightning Jabber"

    def test_aliased_link(self) -> None:
        assert (
            _strip_link_to_name("[[Lightning Jabber|Throwing: Lightning Damage]]")
            == "Throwing: Lightning Damage"
        )

    def test_drops_file_links(self) -> None:
        s = "[[File:icon.png]] [[Hex]] is a rider"
        assert _strip_link_to_name(s) == "Hex is a rider"


class TestParseDRSTable:
    def test_extracts_items_from_fixture(self) -> None:
        fixture = textwrap.dedent(
            """
            Some intro text.

            {| class="wikitable"
            |-
            ! Item !! Tier !! Description !! Notes
            |-
            | [[Lightning Jabber]] || All || 1d4 Lightning rider; treated as Source. ||
            |-
            | [[Arrow of Acid]] || All || 2d4 Acid + permanent surface ||
            |-
            | [[Sword of Life Stealing]] || Two || 10 flat Necrotic on crit || versus non-construct
            |}

            More text.
            """
        ).strip()
        items = parse_drs_table(
            fixture,
            layer_kind=DamageLayerKind.DRS,
            source_category="weapon",
            honour_demotes_to_dr=True,
        )
        # Three rows extracted.
        assert {i.name for i in items} == {
            "Lightning Jabber",
            "Arrow of Acid",
            "Sword of Life Stealing",
        }
        # Dice extraction sniffs the first NdM in the row.
        by_name = {i.name: i for i in items}
        assert by_name["Lightning Jabber"].rider_dice is not None
        assert by_name["Lightning Jabber"].rider_dice.raw == "1d4"
        assert by_name["Lightning Jabber"].damage_type == DamageType.LIGHTNING
        assert by_name["Arrow of Acid"].rider_dice.raw == "2d4"
        assert by_name["Arrow of Acid"].damage_type == DamageType.ACID
        # Honour-mode demotion is propagated from caller.
        assert all(i.honour_demotes_to_dr for i in items)
        # Sword of Life Stealing has no NdM expression — still returned, dice=None.
        assert by_name["Sword of Life Stealing"].rider_dice is None

    def test_no_table_no_items(self) -> None:
        assert parse_drs_table("plain prose, no wikitable") == []


# ── Database round-trip ────────────────────────────────────────────────────


class TestDRSItemDB:
    def test_round_trip(self, tmp_path: Path) -> None:
        db = SpellDB(tmp_path / "drs.db")
        item = DRSItem(
            name="Test Item",
            wiki_url="https://bg3.wiki/wiki/Test",
            layer_kind=DamageLayerKind.DRS,
            rider_dice=None,
            damage_type=DamageType.FIRE,
            honour_demotes_to_dr=True,
            source_category="weapon",
            notes="hand-authored",
        )
        db.upsert_drs_item(item)
        rows = db.list_drs_items()
        assert len(rows) == 1
        assert rows[0]["name"] == "Test Item"
        assert rows[0]["layer_kind"] == "DRS"
        assert rows[0]["honour_demotes_to_dr"] == 1
        # Idempotent upsert — second call must NOT duplicate.
        db.upsert_drs_item(item)
        assert db.count_drs_items() == 1
        # Filter by kind.
        assert db.list_drs_items(layer_kind="DRS")[0]["name"] == "Test Item"
        assert db.list_drs_items(layer_kind="DR") == []
        db.close()


# ── Python ↔ Lean drift check ──────────────────────────────────────────────


class TestLeanExportDriftFree:
    def test_seed_loads(self) -> None:
        seed = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
        assert "items" in seed and isinstance(seed["items"], list)
        assert len(seed["items"]) >= 10, "seed list should be non-trivial"

    def test_committed_lean_matches_generator(self) -> None:
        """
        The committed `Axioms/DRSItems.lean` must be byte-identical to
        what `drs_lean_export.render_lean` produces from the JSON seed.

        If this fails, regenerate via:
            python3 -m src.1_auto_formalizer.drs_lean_export
        and commit the result.
        """
        seed = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
        expected = render_lean(seed)
        actual = DEFAULT_LEAN.read_text(encoding="utf-8")
        if actual != expected:
            # Print a small diff hint to make CI failures actionable.
            from difflib import unified_diff

            diff = "".join(
                unified_diff(
                    actual.splitlines(keepends=True),
                    expected.splitlines(keepends=True),
                    fromfile="committed Axioms/DRSItems.lean",
                    tofile="render_lean(seed)",
                    n=3,
                )
            )
            pytest.fail(
                "Lean DRSItems file is out of sync with the JSON seed.\n"
                "Regenerate via: python3 -m src.1_auto_formalizer.drs_lean_export\n\n"
                + diff[:4000]
            )

    def test_render_includes_every_seed_item(self) -> None:
        seed = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
        text = render_lean(seed)
        for item in seed["items"]:
            assert item["name"] in text, f"missing {item['name']!r} in Lean export"

    def test_drs_items_are_marked_honour_demotes(self) -> None:
        """
        The wiki documents that all DRS items are demoted to plain DR in
        Honour mode.  The seed JSON must reflect this for every DRS entry,
        because `Axioms/DRSItems.lean` proves a theorem of that exact form.
        """
        seed = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
        drs = [i for i in seed["items"] if i["layer_kind"] == "DRS"]
        assert drs, "seed must contain at least one DRS item"
        for item in drs:
            assert item["honour_demotes_to_dr"] is True, item["name"]
