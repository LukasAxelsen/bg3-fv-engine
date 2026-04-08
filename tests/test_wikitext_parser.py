"""
Tests for ``{{Feature page}}`` parsing using real bg3.wiki template patterns.
"""

from __future__ import annotations

from auto_formalizer.models import CastingResource, DamageType, SaveAbility, School
from auto_formalizer.wikitext_parser import parse_spell


# Strings follow bg3.wiki spell infobox parameter names (pipe-separated).
FIREBALL_WIKITEXT = (
    "{{Feature page|type=spell|level=3|school=Evocation|damage=8d6|damage type=Fire|"
    "cost=action, spell3|save=DEX|on save=Targets still take half damage.|"
    "range m=18|aoe=radius|aoe m=4|uid=Projectile_Fireball|"
    "summary=A bright streak flashes from your pointing finger to a point you choose "
    "within range}} "
)

HEX_WIKITEXT = (
    "{{Feature page|type=spell|level=1|school=Enchantment|damage=1d6|damage type=Necrotic|"
    "cost=bonus action, spell1|concentration=yes|uid=Target_Hex|"
    "summary=You place a curse on a creature you can see within range}}"
)

HASTE_WIKITEXT = (
    "{{Feature page|type=spell|level=3|school=Transmutation|cost=action, spell3|"
    "concentration=yes|condition 1=Hastened|condition 1 duration=10|"
    "condition 2=Lethargic|condition 2 duration=1|uid=Target_Haste|"
    "summary=Until the spell ends, the target's speed is doubled}} "
)

ELDRITCH_BLAST_WIKITEXT = (
    "{{Feature page|type=spell|level=cantrip|school=Evocation|damage=1d10|damage type=Force|"
    "cost=action|attack roll=yes|uid=Projectile_EldritchBlast|"
    "summary=A beam of crackling energy streaks toward a creature within range}}"
)

COUNTERSPELL_WIKITEXT = (
    "{{Feature page|type=spell|level=3|school=Abjuration|cost=reaction, spell3|"
    "uid=Target_Counterspell|summary=You attempt to interrupt a creature in the process "
    "of casting a spell}}"
)


def test_parse_fireball_bg3_wiki_template() -> None:
    spell, errors = parse_spell("Fireball", FIREBALL_WIKITEXT)
    assert spell is not None
    assert not errors
    assert spell.level == 3
    assert spell.school == School.EVOCATION
    assert spell.damage_dice is not None and spell.damage_dice.raw == "8d6"
    assert spell.damage_type == DamageType.FIRE
    assert spell.casting_resource == CastingResource.ACTION
    assert spell.spell_slot_level == 3
    assert spell.save_ability == SaveAbility.DEX
    assert spell.on_save and "half" in spell.on_save.lower()
    assert spell.range_m == 18.0
    assert spell.aoe_shape == "radius"
    assert spell.aoe_m == 4.0
    assert spell.uid == "Projectile_Fireball"


def test_parse_hex_enchantment_necrotic_bonus_concentration() -> None:
    spell, errors = parse_spell("Hex", HEX_WIKITEXT)
    assert spell is not None
    assert spell.level == 1
    assert spell.school == School.ENCHANTMENT
    assert spell.damage_dice is not None and spell.damage_dice.raw == "1d6"
    assert spell.damage_type == DamageType.NECROTIC
    assert spell.casting_resource == CastingResource.BONUS_ACTION
    assert spell.spell_slot_level == 1
    assert spell.concentration is True


def test_parse_haste_transmutation_conditions() -> None:
    spell, errors = parse_spell("Haste", HASTE_WIKITEXT)
    assert spell is not None
    assert spell.level == 3
    assert spell.school == School.TRANSMUTATION
    assert spell.damage_dice is None
    assert spell.concentration is True
    assert len(spell.conditions) == 2
    assert spell.conditions[0].name == "Hastened"
    assert spell.conditions[0].duration_turns == 10
    assert spell.conditions[1].name == "Lethargic"
    assert spell.conditions[1].duration_turns == 1


def test_parse_eldritch_blast_cantrip_force_attack() -> None:
    spell, errors = parse_spell("Eldritch Blast", ELDRITCH_BLAST_WIKITEXT)
    assert spell is not None
    assert spell.level == 0
    assert spell.school == School.EVOCATION
    assert spell.damage_dice is not None and spell.damage_dice.raw == "1d10"
    assert spell.damage_type == DamageType.FORCE
    assert spell.requires_attack_roll is True


def test_parse_counterspell_reaction_abjuration() -> None:
    spell, errors = parse_spell("Counterspell", COUNTERSPELL_WIKITEXT)
    assert spell is not None
    assert spell.level == 3
    assert spell.school == School.ABJURATION
    assert spell.casting_resource == CastingResource.REACTION
    assert spell.spell_slot_level == 3


def test_edge_case_missing_feature_template() -> None:
    spell, errors = parse_spell("Gone", "Just prose with no template.")
    assert spell is None
    assert errors


def test_edge_case_unknown_school() -> None:
    w = (
        "{{Feature page|type=spell|level=2|school=Chronurgy|damage=2d4|damage type=Fire|"
        "cost=action, spell2|uid=Fake_UID}}"
    )
    spell, errors = parse_spell("FakeSpell", w)
    assert spell is not None
    assert spell.school is None
    assert any("Unknown school" in e for e in errors)


def test_edge_case_bad_dice_notation() -> None:
    w = (
        "{{Feature page|type=spell|level=1|school=Evocation|damage=XdY|damage type=Fire|"
        "cost=action, spell1|uid=BadDice_UID}}"
    )
    spell, errors = parse_spell("BadDice", w)
    assert spell is not None
    assert spell.damage_dice is None
