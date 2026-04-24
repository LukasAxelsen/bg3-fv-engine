"""
Provenance regression test for ``Axioms/BG3Rules.lean``.

Every axiom in the formal core is supposed to encode a wiki-documented
mechanic.  Without this test, an axiom can quietly drift away from the
wiki numbers (or be added without provenance) and no one notices.

The test consumes ``dataset/axiom_provenance.json`` as a hand-curated
single source of truth and enforces three invariants:

1. **Coverage**: every ``axiom`` declaration in
   ``Axioms/BG3Rules.lean`` has a matching JSON entry by name.
2. **Numeric consistency**: where the JSON entry pins down a
   ``DamageRoll`` shape (e.g. Fireball's 8d6 Fire), the corresponding
   substring is present *verbatim* in the Lean file.
3. **DB faithfulness (optional)**: if the live ``dataset/valor.db``
   file exists, the spell row recorded by the crawler must agree with
   the JSON.  This is conditional so that contributors without a fresh
   crawl can still run the suite (CI runs always exercise (1)+(2)).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from auto_formalizer.database import SpellDB
from auto_formalizer.models import DiceExpression

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = REPO_ROOT / "dataset" / "axiom_provenance.json"
LEAN_FILE = REPO_ROOT / "src" / "2_fv_core" / "Axioms" / "BG3Rules.lean"
DB_PATH = REPO_ROOT / "dataset" / "valor.db"

_AXIOM_DECL_RE = re.compile(r"^\s*axiom\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def _load_provenance() -> dict:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def _read_lean() -> str:
    return LEAN_FILE.read_text(encoding="utf-8")


def _declared_axioms() -> set[str]:
    return set(_AXIOM_DECL_RE.findall(_read_lean()))


# ── Coverage ───────────────────────────────────────────────────────────────


class TestCoverage:
    def test_every_lean_axiom_has_provenance(self) -> None:
        prov = _load_provenance()
        prov_names = {entry["axiom_name"] for entry in prov["axioms"]}
        declared = _declared_axioms()
        missing = declared - prov_names
        assert not missing, (
            f"Lean axioms without provenance entries in dataset/axiom_provenance.json: "
            f"{sorted(missing)}"
        )

    def test_no_orphan_provenance(self) -> None:
        prov = _load_provenance()
        prov_names = {entry["axiom_name"] for entry in prov["axioms"]}
        declared = _declared_axioms()
        orphans = prov_names - declared
        assert not orphans, (
            f"Provenance entries without a corresponding `axiom` in BG3Rules.lean: "
            f"{sorted(orphans)} (delete the entry or add the axiom back)."
        )

    def test_all_provenance_entries_have_required_fields(self) -> None:
        prov = _load_provenance()
        for entry in prov["axioms"]:
            assert "axiom_name" in entry
            assert "spell_name" in entry
            assert "wiki_url" in entry, entry["axiom_name"]
            assert entry["wiki_url"].startswith("https://bg3.wiki/"), entry["axiom_name"]


# ── Numeric consistency ────────────────────────────────────────────────────


class TestNumericPatterns:
    def test_lean_pattern_present_when_specified(self) -> None:
        prov = _load_provenance()
        text = _read_lean()
        failures: list[str] = []
        for entry in prov["axioms"]:
            single = entry.get("lean_dice_pattern")
            if single:
                if single not in text:
                    failures.append(f"{entry['axiom_name']}: {single!r} not in BG3Rules.lean")
            for pat_key in ("lean_dice_pattern_normal", "lean_dice_pattern_crit"):
                pat = entry.get(pat_key)
                if pat and pat not in text:
                    failures.append(
                        f"{entry['axiom_name']} ({pat_key}): {pat!r} not in BG3Rules.lean"
                    )
        assert not failures, (
            "axiom_provenance.json declares dice patterns that are not present "
            "verbatim in BG3Rules.lean:\n  " + "\n  ".join(failures)
        )

    def test_dice_consistent_with_pattern(self) -> None:
        """If ``dice`` (or ``dice_normal``/``dice_crit``) is provided, ensure
        the pattern string actually contains those numbers — protects against
        someone changing the pattern without updating the dice fields (or vice
        versa)."""
        prov = _load_provenance()
        for entry in prov["axioms"]:
            if entry.get("lean_dice_pattern") and entry.get("dice"):
                d = entry["dice"]
                pat = entry["lean_dice_pattern"]
                assert str(d["count"]) in pat, entry["axiom_name"]
                assert str(d["sides"]) in pat, entry["axiom_name"]
            for dk, pk in (
                ("dice_normal", "lean_dice_pattern_normal"),
                ("dice_crit", "lean_dice_pattern_crit"),
            ):
                if entry.get(dk) and entry.get(pk):
                    d = entry[dk]
                    pat = entry[pk]
                    assert str(d["count"]) in pat, f"{entry['axiom_name']}.{dk}"
                    assert str(d["sides"]) in pat, f"{entry['axiom_name']}.{dk}"


# ── DB faithfulness (optional) ─────────────────────────────────────────────


@pytest.mark.skipif(not DB_PATH.exists(), reason="dataset/valor.db not present")
class TestDBFaithfulness:
    @pytest.fixture(scope="class")
    def db(self):
        d = SpellDB(DB_PATH)
        try:
            yield d
        finally:
            d.close()

    def test_spell_dice_match_provenance(self, db) -> None:
        prov = _load_provenance()
        failures: list[str] = []
        for entry in prov["axioms"]:
            spell_name = entry.get("spell_name")
            if not spell_name or spell_name.startswith("("):
                continue  # skip non-spell rows like "(general rule)"
            row = db.get_spell_by_name(spell_name)
            if row is None:
                # Crawler hasn't picked up this spell — informational, not fatal.
                continue
            wiki_dice = row.get("damage_dice")
            wiki_type = row.get("damage_type")
            for dk in ("dice", "dice_normal"):
                if entry.get(dk):
                    expected = DiceExpression(
                        count=entry[dk]["count"],
                        sides=entry[dk]["sides"],
                        bonus=entry[dk].get("bonus", 0),
                        raw=f"{entry[dk]['count']}d{entry[dk]['sides']}",
                    )
                    if wiki_dice != expected.raw:
                        failures.append(
                            f"{entry['axiom_name']}: provenance dice {expected.raw!r} "
                            f"!= SpellDB {wiki_dice!r} for {spell_name!r}"
                        )
                    if wiki_type and entry.get("damage_type") and wiki_type != entry["damage_type"]:
                        failures.append(
                            f"{entry['axiom_name']}: provenance damage_type "
                            f"{entry['damage_type']!r} != SpellDB {wiki_type!r}"
                        )
                    break  # only check one of dice/dice_normal
        assert not failures, "\n".join(failures)
