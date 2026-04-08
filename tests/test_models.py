"""Pydantic model and dice parsing tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_formalizer.models import DamageType, DiceExpression, School, Spell


def test_dice_expression_parse_standard_notation() -> None:
    d = DiceExpression.parse("8d6")
    assert d is not None
    assert d.count == 8 and d.sides == 6 and d.bonus == 0
    assert d.raw == "8d6"


def test_dice_expression_parse_with_bonus() -> None:
    d = DiceExpression.parse("1d10+3")
    assert d is not None
    assert d.count == 1 and d.sides == 10 and d.bonus == 3


def test_dice_expression_parse_bonus_with_spaces() -> None:
    d = DiceExpression.parse("1d10 + 3")
    assert d is not None
    assert d.bonus == 3


def test_dice_expression_invalid_returns_none() -> None:
    assert DiceExpression.parse("not dice") is None
    assert DiceExpression.parse("100d6d6") is None


def test_spell_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Spell(
            name="   ",
            wiki_url="https://bg3.wiki/wiki/X",
            uid="UID",
            level=0,
        )


def test_spell_level_bounds() -> None:
    with pytest.raises(ValidationError):
        Spell(
            name="Bad",
            wiki_url="https://bg3.wiki/wiki/Bad",
            uid="UID",
            level=10,
        )
    Spell(
        name="Nine",
        wiki_url="https://bg3.wiki/wiki/Nine",
        uid="UID",
        level=9,
    )


def test_damage_type_enum_bg3_values() -> None:
    assert DamageType.FIRE.value == "Fire"
    assert DamageType.FORCE.value == "Force"
    assert DamageType.NECROTIC.value == "Necrotic"
    assert DamageType.ACID.value == "Acid"


def test_school_enum_roundtrip() -> None:
    assert School("Transmutation") == School.TRANSMUTATION
