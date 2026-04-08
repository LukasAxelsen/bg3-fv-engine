"""SQLite persistence tests (temporary DB per test)."""

from __future__ import annotations

import sqlite3

import pytest

from auto_formalizer.database import SpellDB
from auto_formalizer.models import CastingResource, School, Spell


def _minimal_spell(**kwargs) -> Spell:
    base = dict(
        name="Test Spell",
        wiki_url="https://bg3.wiki/wiki/Test_Spell",
        uid="UID_Test",
        level=1,
        school=School.EVOCATION,
        raw_wikitext="{{Feature page|type=spell|level=1|school=Evocation|uid=UID_Test}}",
    )
    base.update(kwargs)
    return Spell(**base)


def test_upsert_and_retrieval(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    spell = _minimal_spell(name="Magic Missile", uid="Projectile_MagicMissile")
    with SpellDB(db_path) as db:
        db.upsert_spell(spell)
        row = db.get_spell("Projectile_MagicMissile")
        assert row is not None
        assert row["name"] == "Magic Missile"
        assert row["level"] == 1
        by_name = db.get_spell_by_name("Magic Missile")
        assert by_name is not None
        assert by_name["uid"] == "Projectile_MagicMissile"


def test_duplicate_uid_upsert_updates(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(_minimal_spell(name="Hex", uid="Target_Hex", level=1))
        db.upsert_spell(
            _minimal_spell(
                name="Hex",
                uid="Target_Hex",
                level=2,
                summary="updated",
            )
        )
        row = db.get_spell("Target_Hex")
        assert row is not None
        assert row["level"] == 2
        assert row["summary"] == "updated"


def test_duplicate_name_different_uid_conflict(tmp_path) -> None:
    """Second insert with same name but different uid violates UNIQUE(name)."""
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(_minimal_spell(name="SameName", uid="UID_A"))
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_spell(_minimal_spell(name="SameName", uid="UID_B"))


def test_query_by_level(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(_minimal_spell(name="Cantrip", uid="C1", level=0))
        db.upsert_spell(_minimal_spell(name="Level3", uid="L3", level=3))
        z = db.list_spells(level=0)
        assert len(z) == 1
        assert z[0]["name"] == "Cantrip"


def test_spells_with_bugs(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(_minimal_spell(name="Clean", uid="U1", bugs=[]))
        db.upsert_spell(_minimal_spell(name="Buggy", uid="U2", bugs=["Listed on bg3.wiki bugs section"]))
        buggy = db.spells_with_bugs()
        assert len(buggy) == 1
        assert buggy[0]["name"] == "Buggy"


def test_spells_with_concentration(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(_minimal_spell(name="Conc", uid="C1", concentration=True))
        db.upsert_spell(_minimal_spell(name="Snap", uid="S1", concentration=False))
        rows = db.spells_with_concentration()
        assert len(rows) == 1
        assert rows[0]["name"] == "Conc"


def test_reaction_spells(tmp_path) -> None:
    db_path = tmp_path / "spells.db"
    with SpellDB(db_path) as db:
        db.upsert_spell(
            _minimal_spell(
                name="Counterspell",
                uid="Target_Counterspell",
                casting_resource=CastingResource.REACTION,
            )
        )
        db.upsert_spell(_minimal_spell(name="Fireball", uid="Projectile_Fireball"))
        rx = db.reaction_spells()
        assert len(rx) == 1
        assert rx[0]["casting_resource"] == "Reaction"
